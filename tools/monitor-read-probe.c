// SPDX-License-Identifier: GPL-2.0-or-later
/* Temporary read-only probe of the exact Eleven Rack monitoring addresses.
 * Never binds an interface, detaches a driver, or sends OUT requests.
 */
#include <linux/module.h>
#include <linux/slab.h>
#include <linux/usb.h>

static unsigned int request = 3; /* UAC2 MEM (3) or CUR (1), IN direction */
module_param(request, uint, 0444);
static char results[2048];
module_param_string(results, results, sizeof(results), 0444);

struct find_rack { struct usb_device *dev; unsigned int count; };

static int find_rack(struct usb_device *dev, void *data)
{
	struct find_rack *rack = data;

	if (le16_to_cpu(dev->descriptor.idVendor) == 0x0dba &&
	    le16_to_cpu(dev->descriptor.idProduct) == 0xb011) {
		if (!rack->count)
			rack->dev = usb_get_dev(dev);
		rack->count++;
	}
	return 0;
}

static int __init monitor_read_init(void)
{
	struct find_rack rack = {};
	struct usb_interface *intf;
	u8 *data;
	int err, input, offset = 0, length, wanted;
	u16 value, index;

	if (request != 1 && request != 3)
		return -EINVAL;
	usb_for_each_dev(&rack, find_rack);
	if (rack.count != 1) {
		if (rack.dev)
			usb_put_dev(rack.dev);
		return -ENODEV;
	}
	usb_lock_device(rack.dev);
	intf = usb_ifnum_to_if(rack.dev, 1);
	if (intf)
		usb_get_intf(intf);
	usb_unlock_device(rack.dev);
	if (!intf) {
		err = -ENODEV;
		goto put_device;
	}
	err = usb_autopm_get_interface(intf);
	if (err < 0)
		goto put_interface;
	data = kmalloc(4, GFP_KERNEL);
	if (!data) {
		err = -ENOMEM;
		goto put_pm;
	}
	for (input = -1; input < 8; input++) {
		value = input < 0 ? 0 : 0x27 + 6 * input;
		index = input < 0 ? 0x2001 : 0x4001;
		wanted = input < 0 ? 1 : 4;
		memset(data, 0, 4);
		length = usb_control_msg(rack.dev, usb_rcvctrlpipe(rack.dev, 0),
			request, USB_DIR_IN | USB_TYPE_CLASS | USB_RECIP_INTERFACE,
			value, index, data, wanted, 500);
		offset += scnprintf(results + offset, sizeof(results) - offset,
			"%02x,%04x,%04x,%d,%d,%*phN\n", request, value, index,
			wanted, length, length > 0 ? min(length, 4) : 0, data);
	}
	kfree(data);
	err = 0;
put_pm:
	usb_autopm_put_interface(intf);
put_interface:
	usb_put_intf(intf);
put_device:
	usb_put_dev(rack.dev);
	return err;
}

static void __exit monitor_read_exit(void) {}
module_init(monitor_read_init);
module_exit(monitor_read_exit);
MODULE_LICENSE("GPL");
MODULE_DESCRIPTION("Bounded read-only Eleven Rack monitoring protocol probe");
