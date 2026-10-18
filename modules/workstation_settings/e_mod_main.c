/* SPDX-License-Identifier: GPL-3.0-only
 * Native settings entry points and scoped default-wallpaper access.
 */
#include "e.h"
#include <string.h>
#include <sys/stat.h>
#include <unistd.h>
E_API E_Module_Api e_modapi = { E_MODULE_API_VERSION, "Workstation Settings Bridge" };
static Eldbus_Service_Interface *service;
static Ecore_Timer *restart_timer;
static const char *paths[] = {
 "appearance/theme", "appearance/wallpaper", "appearance/fonts",
 "appearance/scale", "appearance/borders", "appearance/colors",
 "appearance/xsettings", "appearance/transitions", "extensions/shelves",
 "menus/menu_settings", "screen/virtual_desktops", "windows/window_focus",
 "windows/window_geometry", "windows/window_remembers", "windows/tiling",
 "extensions/notification", "keyboard_and_mouse/key_bindings",
 "keyboard_and_mouse/mouse_settings", "keyboard_and_mouse/xkbswitch",
 "language/language_settings", "screen/screen_saver", "screen/power_management",
 "extensions/modules", "extensions/gadman", "applications/ibar_applications",
 "applications/favorite_applications", "applications/personal_applications",
 "applications/default_applications", "applications/startup_applications", NULL
};
static int allowed(const char *path)
{
 unsigned i;
 for (i=0; paths[i]; ++i) if (!strcmp(path, paths[i])) return 1;
 return 0;
}
static Eldbus_Message *list_cb(const Eldbus_Service_Interface *iface EINA_UNUSED,
                              const Eldbus_Message *msg)
{
 Eldbus_Message *reply = eldbus_message_method_return_new(msg);
 Eldbus_Message_Iter *iter, *array;
 unsigned i;
 if (!reply) return NULL;
 iter = eldbus_message_iter_get(reply);
 if (!eldbus_message_iter_arguments_append(iter, "a(sb)", &array)) return reply;
 for (i=0; paths[i]; ++i)
   {
    Eldbus_Message_Iter *item;
    if (!eldbus_message_iter_arguments_append(array, "(sb)", &item)) break;
    eldbus_message_iter_arguments_append(item, "sb", paths[i],
                                         !!e_configure_registry_exists(paths[i]));
    eldbus_message_iter_container_close(array, item);
   }
 eldbus_message_iter_container_close(iter, array);
 return reply;
}
static Eldbus_Message *open_cb(const Eldbus_Service_Interface *iface EINA_UNUSED,
                              const Eldbus_Message *msg)
{
 const char *path;
 if (!eldbus_message_arguments_get(msg, "s", &path) || !allowed(path))
   return eldbus_message_error_new(msg, "org.auzietek.WorkstationSettings.InvalidEntry",
                                   "Choose a supported settings entry.");
 if (!e_configure_registry_exists(path))
   return eldbus_message_error_new(msg, "org.auzietek.WorkstationSettings.Unavailable",
                                   "This E settings module is not loaded.");
 e_configure_registry_call(path, NULL, NULL);
 return eldbus_message_method_return_new(msg);
}
static Eldbus_Message *appearance_cb(const Eldbus_Service_Interface *iface EINA_UNUSED,
                                    const Eldbus_Message *msg)
{
 Eldbus_Message *reply = eldbus_message_method_return_new(msg);
 const char *theme = e_theme_edje_file_get("base/theme", "e/widgets/border/default/border");
 eldbus_message_arguments_append(reply, "ssud", theme ? theme : "",
   e_config->desktop_default_background ? e_config->desktop_default_background : "",
   eina_list_count(e_config->desktop_backgrounds), e_scale);
 return reply;
}
static Eldbus_Message *wallpaper_cb(const Eldbus_Service_Interface *iface EINA_UNUSED,
                                   const Eldbus_Message *msg)
{
 const char *file, *expected;
 struct stat st;
 if (!eldbus_message_arguments_get(msg, "ss", &file, &expected))
   return eldbus_message_error_new(msg, "org.auzietek.WorkstationSettings.InvalidWallpaper", "Choose an installed wallpaper.");
 if (strcmp(expected, e_config->desktop_default_background ? e_config->desktop_default_background : ""))
   return eldbus_message_error_new(msg, "org.auzietek.WorkstationSettings.Changed", "Wallpaper changed elsewhere. Refresh before applying.");
 if (*file && (file[0] != '/' || stat(file, &st) || !S_ISREG(st.st_mode) ||
     st.st_size > 64*1024*1024 || access(file, R_OK) ||
     !eina_str_has_extension(file, ".edj") ||
     !edje_file_group_exists(file, "e/desktop/background")))
   return eldbus_message_error_new(msg, "org.auzietek.WorkstationSettings.InvalidWallpaper", "Select a readable E wallpaper (up to 64 MiB).");
 /* Deliberately preserve per-screen/workspace overrides. */
 e_bg_default_set(*file ? file : NULL);
 e_bg_update();
 e_config_save_queue();
 return eldbus_message_method_return_new(msg);
}
static Eina_Bool restart_theme(void *data EINA_UNUSED)
{
 E_Action *action=e_action_find("restart");restart_timer=NULL;
 if(action && action->func.go)action->func.go(NULL,NULL);
 return ECORE_CALLBACK_CANCEL;
}
static Eldbus_Message *theme_cb(const Eldbus_Service_Interface *iface EINA_UNUSED,const Eldbus_Message *msg)
{
 const char *file,*expected,*current,*group;struct stat st;
 Eina_List *groups,*l;Eina_Bool valid=EINA_FALSE;
 if(!eldbus_message_arguments_get(msg,"ss",&file,&expected))
   return eldbus_message_error_new(msg,"org.auzietek.WorkstationSettings.InvalidTheme","Select a desktop theme.");
 current=e_theme_edje_file_get("base/theme","e/widgets/border/default/border");
 if(restart_timer || strcmp(current?current:"",expected))
   return eldbus_message_error_new(msg,"org.auzietek.WorkstationSettings.Changed","Theme changed or restart is pending. Refresh before applying.");
 if(file[0]!='/' || strchr(file,':') || stat(file,&st) || !S_ISREG(st.st_mode) || st.st_size>64*1024*1024 || access(file,R_OK) || !eina_str_has_extension(file,".edj"))
   return eldbus_message_error_new(msg,"org.auzietek.WorkstationSettings.InvalidTheme","Select a readable desktop theme (up to 64 MiB).");
 groups=edje_file_collection_list(file);
 EINA_LIST_FOREACH(groups,l,group)if(!strncmp(group,"e/widgets/border/",17)){valid=EINA_TRUE;break;}
 edje_file_collection_list_free(groups);
 if(!valid)return eldbus_message_error_new(msg,"org.auzietek.WorkstationSettings.InvalidTheme","This file does not provide E desktop window styles.");
 E_Action *action=e_action_find("restart");
 if(!action || !action->func.go)return eldbus_message_error_new(msg,"org.auzietek.WorkstationSettings.Unavailable","Desktop restart is unavailable.");
 char *previous=strdup(elm_theme_get(NULL));
 if(!previous)return eldbus_message_error_new(msg,"org.auzietek.WorkstationSettings.Unavailable","Cannot retain the previous theme.");
 restart_timer=ecore_timer_add(0.5,restart_theme,NULL);
 if(!restart_timer){free(previous);return eldbus_message_error_new(msg,"org.auzietek.WorkstationSettings.Unavailable","Cannot schedule the desktop restart.");}
 /* A full theme element path avoids ambiguous duplicate basenames. */
 elm_theme_set(NULL,file);
 if(!elm_config_save()){
   elm_theme_set(NULL,previous);ecore_timer_del(restart_timer);restart_timer=NULL;free(previous);
   return eldbus_message_error_new(msg,"org.auzietek.WorkstationSettings.SaveFailed","Theme could not be saved; the previous theme was restored.");
 }
 elm_config_all_flush();free(previous);
 return eldbus_message_method_return_new(msg);
}
static const Eldbus_Method methods[] = {
 { "SetTheme", ELDBUS_ARGS({"s", "file"}, {"s", "expected"}), NULL, theme_cb, 0 },
 { "Appearance", NULL, ELDBUS_ARGS({"s", "theme"}, {"s", "wallpaper"}, {"u", "overrides"}, {"d", "scale"}), appearance_cb, 0 },
 { "SetWallpaper", ELDBUS_ARGS({"s", "file"}, {"s", "expected"}), NULL, wallpaper_cb, 0 },
 { "List", NULL, ELDBUS_ARGS({"a(sb)", "entries"}), list_cb, 0 },
 { "Open", ELDBUS_ARGS({"s", "entry"}), NULL, open_cb, 0 },
 { NULL, NULL, NULL, NULL, 0 }
};
static const Eldbus_Service_Interface_Desc descriptor = {
 "org.auzietek.WorkstationSettings", methods, NULL, NULL, NULL, NULL
};
E_API void *e_modapi_init(E_Module *m)
{
 service = e_msgbus_interface_attach(&descriptor);
 return service ? m : NULL;
}
E_API int e_modapi_shutdown(E_Module *m EINA_UNUSED)
{
 if(restart_timer){ecore_timer_del(restart_timer);restart_timer=NULL;}
 if (service) eldbus_service_interface_unregister(service);
 service = NULL;
 return 1;
}
E_API int e_modapi_save(E_Module *m EINA_UNUSED) { return 1; }
