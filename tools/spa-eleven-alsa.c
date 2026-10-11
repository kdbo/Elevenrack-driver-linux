/* SPDX-License-Identifier: MIT
 * Factory entry for an experimental PCM-only PipeWire ALSA backend.
 * Keep enumeration/ACP/other devices on the distribution's ALSA plugin.
 */
#include <errno.h>
#include <dlfcn.h>
#include <string.h>
#include <spa/support/plugin.h>
#include <spa/support/log.h>
#ifndef ELEVEN_SYSTEM_ALSA_PLUGIN
#error "Build with ELEVEN_SYSTEM_ALSA_PLUGIN pointing to the distribution ALSA plugin"
#endif
extern const struct spa_handle_factory spa_alsa_source_factory;
extern const struct spa_handle_factory spa_alsa_sink_factory;
extern const struct spa_handle_factory spa_alsa_pcm_device_factory;
SPA_LOG_TOPIC_DEFINE(alsa_log_topic, "spa.alsa");
SPA_LOG_TOPIC_ENUM_DEFINE_REGISTERED;
SPA_EXPORT int spa_handle_factory_enum(const struct spa_handle_factory **factory, uint32_t *index)
{
    if (!factory || !index) return -EINVAL;
    switch (*index) {
    case 0: (*index)++; *factory = &spa_alsa_source_factory; return 1;
    case 1: (*index)++; *factory = &spa_alsa_sink_factory; return 1;
    case 2: (*index)++; *factory = &spa_alsa_pcm_device_factory; return 1;
    default: break;
    }
    /* Retain the distribution's enumerator, ACP and MIDI factories. */
    static void *original;
    static int (*enumerate)(const struct spa_handle_factory **, uint32_t *);
    if (!original) {
        original = dlopen(ELEVEN_SYSTEM_ALSA_PLUGIN, RTLD_NOW | RTLD_LOCAL);
        if (!original) return -ENOENT;
        enumerate = dlsym(original, "spa_handle_factory_enum");
        if (!enumerate) return -ENOSYS;
    }
    uint32_t offset = *index-3;
    int result;
    while ((result = enumerate(factory, &offset)) > 0) {
        *index = offset+3;
        if (strcmp((*factory)->name, spa_alsa_source_factory.name) &&
            strcmp((*factory)->name, spa_alsa_sink_factory.name) &&
            strcmp((*factory)->name, spa_alsa_pcm_device_factory.name)) return result;
    }
    return result;
}
