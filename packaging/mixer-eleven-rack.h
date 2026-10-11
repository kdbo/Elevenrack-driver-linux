/* SPDX-License-Identifier: GPL-2.0-or-later */
/* Eleven Rack monitor protocol supplied by Paul Bender, R11 Audio. */
#include <linux/mutex.h>

struct eleven_monitor {
	struct usb_mixer_elem_list head;
	struct mutex lock;
	unsigned int mode; /* Last observation; get always reads the device. */
};

static int eleven_monitor_write(struct usb_mixer_interface *mixer, u16 value,
				u16 index, void *data, u16 size)
{
	int err = snd_usb_ctl_msg(mixer->chip->dev,
		usb_sndctrlpipe(mixer->chip->dev, 0), 0x03,
		USB_DIR_OUT | USB_TYPE_CLASS | USB_RECIP_INTERFACE,
		value, index, data, size);

	return err < 0 ? err : (err == size ? 0 : -EIO);
}

static int eleven_monitor_info(struct snd_kcontrol *kctl,
			       struct snd_ctl_elem_info *uinfo)
{
	static const char * const names[] = { "Unknown", "Hardware", "DAW Only", "Software Mix" };

	return snd_ctl_enum_info(uinfo, 1, ARRAY_SIZE(names), names);
}

static int eleven_monitor_read(struct usb_mixer_interface *mixer, u16 value,
			       u16 index, void *data, u16 size)
{
	int err = snd_usb_ctl_msg(mixer->chip->dev,
		usb_rcvctrlpipe(mixer->chip->dev, 0), 0x03,
		USB_DIR_IN | USB_TYPE_CLASS | USB_RECIP_INTERFACE,
		value, index, data, size);

	return err < 0 ? err : (err == size ? 0 : -EIO);
}

static int eleven_monitor_read_mode(struct usb_mixer_interface *mixer,
				    unsigned int *mode)
{
	u8 gate, gains[4];
	int err, input;

	*mode = 0;
	err = eleven_monitor_read(mixer, 0, 0x2001, &gate, 1);
	if (err < 0)
		return err;
	/* Hardware ignores the software crosspoint gains, which can stay muted. */
	if (gate == 2) {
		*mode = 1;
		return 0;
	}
	if (gate != 1)
		return 0;
	for (input = 0; input < 8; input++) {
		err = eleven_monitor_read(mixer, 0x27 + 6 * input, 0x4001,
					  gains, sizeof(gains));
		if (err < 0)
			return err;
		if (gains[0] != 0 || gains[1] != 0x80 ||
		    gains[2] != 0 || gains[3] != 0x80) {
			*mode = 3; /* Software control, but not DAW-only silence. */
			return 0;
		}
	}
	*mode = 2;
	return 0;
}

static int eleven_monitor_get(struct snd_kcontrol *kctl,
			      struct snd_ctl_elem_value *value)
{
	struct eleven_monitor *monitor = snd_kcontrol_chip(kctl);
	struct usb_mixer_interface *mixer = monitor->head.mixer;
	int err;

	err = snd_usb_lock_shutdown(mixer->chip);
	if (err < 0)
		return err;
	mutex_lock(&monitor->lock);
	err = eleven_monitor_read_mode(mixer, &monitor->mode);
	value->value.enumerated.item[0] = monitor->mode;
	mutex_unlock(&monitor->lock);
	snd_usb_unlock_shutdown(mixer->chip);
	return err;
}

static int eleven_monitor_put(struct snd_kcontrol *kctl,
			      struct snd_ctl_elem_value *value)
{
	struct eleven_monitor *monitor = snd_kcontrol_chip(kctl);
	struct usb_mixer_interface *mixer = monitor->head.mixer;
	unsigned int mode = value->value.enumerated.item[0];
	unsigned int old_mode, observed;
	u8 gate;
	/* Both signed gains are -infinity (0x8000), little endian. */
	u8 silence[] = { 0x00, 0x80, 0x00, 0x80 };
	int err, input, rollback;

	if (mode != 1 && mode != 2)
		return -EINVAL;
	err = snd_usb_lock_shutdown(mixer->chip);
	if (err < 0)
		return err;
	mutex_lock(&monitor->lock);
	old_mode = monitor->mode;
	/* Always write, then independently verify the complete state. */
	gate = mode == 1 ? 2 : 1;
	err = eleven_monitor_write(mixer, 0, 0x2001, &gate, 1);
	if (err < 0)
		goto failed;
	if (mode == 2) {
		for (input = 0; input < 8; input++) {
			err = eleven_monitor_write(mixer, 0x27 + 6 * input,
						   0x4001, silence, sizeof(silence));
			if (err < 0)
				goto failed;
		}
	}
	err = eleven_monitor_read_mode(mixer, &observed);
	if (err < 0)
		goto failed;
	if (observed != mode) {
		err = -EIO;
		goto failed;
	}
	monitor->mode = observed;
	err = old_mode != mode;
	goto out;
failed:
	/* Do not leave a partially configured mixer under software control. */
	gate = 2;
	rollback = eleven_monitor_write(mixer, 0, 0x2001, &gate, 1);
	monitor->mode = rollback < 0 ? 0 : 1;
	snd_ctl_notify(mixer->chip->card, SNDRV_CTL_EVENT_MASK_VALUE, &kctl->id);
out:
	mutex_unlock(&monitor->lock);
	snd_usb_unlock_shutdown(mixer->chip);
	return err;
}

static int eleven_monitor_resume(struct usb_mixer_elem_list *head)
{
	struct eleven_monitor *monitor = container_of(head, struct eleven_monitor, head);

	/* Resume may reset device state; do not claim the old command still holds. */
	mutex_lock(&monitor->lock);
	monitor->mode = 0;
	mutex_unlock(&monitor->lock);
	snd_ctl_notify(head->mixer->chip->card, SNDRV_CTL_EVENT_MASK_VALUE, &head->kctl->id);
	return 0;
}

static int eleven_rate_info(struct snd_kcontrol *kctl,
			    struct snd_ctl_elem_info *info)
{
	info->type = SNDRV_CTL_ELEM_TYPE_INTEGER;
	info->count = 1;
	info->value.integer.min = 0;
	info->value.integer.max = 192000;
	info->value.integer.step = 1;
	return 0;
}

static int eleven_rate_get(struct snd_kcontrol *kctl,
			   struct snd_ctl_elem_value *value)
{
	struct usb_mixer_elem_list *head = snd_kcontrol_chip(kctl);
	struct usb_mixer_interface *mixer = head->mixer;
	u8 source;
	__le32 frequency;
	unsigned int hz;
	int err;

	err = snd_usb_lock_shutdown(mixer->chip);
	if (err < 0)
		return err;
	/* Read the selector, then its current source (Internal, AES or S/PDIF). */
	err = snd_usb_ctl_msg(mixer->chip->dev,
		usb_rcvctrlpipe(mixer->chip->dev, 0), 0x01, 0xa1,
		0x0100, 0x8001, &source, sizeof(source));
	if (err != sizeof(source)) {
		err = err < 0 ? err : -EIO;
		goto out;
	}
	if (source < 1 || source > 3) {
		err = -EINVAL;
		goto out;
	}
	err = snd_usb_ctl_msg(mixer->chip->dev,
		usb_rcvctrlpipe(mixer->chip->dev, 0), 0x01, 0xa1,
		0x0100, ((0x80 + source) << 8) | 1, &frequency, sizeof(frequency));
	if (err != sizeof(frequency)) {
		err = err < 0 ? err : -EIO;
		goto out;
	}
	hz = le32_to_cpu(frequency);
	if (!hz || hz > 192000) {
		err = -ENODATA;
		goto out;
	}
	value->value.integer.value[0] = hz;
	err = 0;
out:
	snd_usb_unlock_shutdown(mixer->chip);
	return err;
}

static int snd_eleven_rate_create(struct usb_mixer_interface *mixer)
{
	static const struct snd_kcontrol_new control = {
		.iface = SNDRV_CTL_ELEM_IFACE_MIXER,
		.name = "Eleven Rack Sample Rate",
		.access = SNDRV_CTL_ELEM_ACCESS_READ,
		.info = eleven_rate_info,
		.get = eleven_rate_get,
	};
	struct usb_mixer_elem_list *head;
	struct snd_kcontrol *kctl;

	head = kzalloc(sizeof(*head), GFP_KERNEL);
	if (!head)
		return -ENOMEM;
	head->mixer = mixer;
	head->id = 0x80;
	kctl = snd_ctl_new1(&control, head);
	if (!kctl) {
		kfree(head);
		return -ENOMEM;
	}
	kctl->private_free = snd_usb_mixer_elem_free;
	return snd_usb_mixer_add_list(head, kctl, false);
}

static int snd_eleven_monitor_create(struct usb_mixer_interface *mixer)
{
	static const struct snd_kcontrol_new control = {
		.iface = SNDRV_CTL_ELEM_IFACE_MIXER,
		.name = "Eleven Rack Monitoring Mode",
		.info = eleven_monitor_info,
		.get = eleven_monitor_get,
		.put = eleven_monitor_put,
	};
	struct eleven_monitor *monitor;
	struct snd_kcontrol *kctl;
	int err;

	if (mixer->hostif->desc.bInterfaceNumber != 1)
		return 0;
	monitor = kzalloc(sizeof(*monitor), GFP_KERNEL);
	if (!monitor)
		return -ENOMEM;
	monitor->head.mixer = mixer;
	monitor->head.id = 0x20;
	monitor->head.resume = eleven_monitor_resume;
	mutex_init(&monitor->lock);
	kctl = snd_ctl_new1(&control, monitor);
	if (!kctl) {
		kfree(monitor);
		return -ENOMEM;
	}
	kctl->private_free = snd_usb_mixer_elem_free;
	err = snd_usb_mixer_add_list(&monitor->head, kctl, false);
	return err < 0 ? err : snd_eleven_rate_create(mixer);
}
