/* SPDX-License-Identifier: GPL-3.0-only */
#include <Elementary.h>
void accounts_init(Evas_Object *,void (*)(const char *));
void accounts_visible(Eina_Bool);
void accounts_shutdown(void);
void accounts_link_set(void (*)(void));
