/* SPDX-License-Identifier: GPL-3.0-only */
#ifndef WORKSTATION_AUDIO_H
#define WORKSTATION_AUDIO_H
#include <Elementary.h>
void audio_init(Evas_Object *parent,void (*status)(const char *));
void audio_visible(Eina_Bool visible);
const char *audio_status(void);
char *audio_diagnostics(void);
void audio_shutdown(void);
#endif
