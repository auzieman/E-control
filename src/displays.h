/* SPDX-License-Identifier: GPL-3.0-only */
#include <Elementary.h>
void displays_init(Evas_Object *parent, void (*status)(const char *));
void displays_visible(Eina_Bool visible);
const char *displays_status(void);
char *displays_diagnostics(void);
void displays_shutdown(void);
