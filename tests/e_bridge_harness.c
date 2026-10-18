/* SPDX-License-Identifier: GPL-3.0-only
 * Isolated registry stand-in: never links to or changes the running E process.
 */
#include "e.h"
#include <dlfcn.h>
#include <stdio.h>
static Eldbus_Connection *connection;
static E_Config configuration;
E_API E_Config *e_config = &configuration;
E_API double e_scale = 1.25;
static char *test_theme;
EAPI const char *elm_theme_get(Elm_Theme *th EINA_UNUSED){return test_theme?test_theme:"/fixture/theme.edj";}
EAPI void elm_theme_set(Elm_Theme *th EINA_UNUSED,const char *file){free(test_theme);test_theme=strdup(file);}
EAPI Eina_Bool elm_config_save(void){return !strstr(elm_theme_get(NULL),"fail.edj");}
EAPI void elm_config_all_flush(void){}
static void fake_restart(E_Object *o EINA_UNUSED,const char *params EINA_UNUSED){puts("RESTART");fflush(stdout);}
E_API E_Action *e_action_find(const char *name){static E_Action action;action.func.go=fake_restart;return !strcmp(name,"restart")?&action:NULL;}
E_API const char *e_theme_edje_file_get(const char *category EINA_UNUSED,const char *group EINA_UNUSED){return elm_theme_get(NULL);}
E_API void e_bg_default_set(const char *file){eina_stringshare_replace(&e_config->desktop_default_background,file);}
E_API void e_bg_update(void){}
E_API void e_config_save_queue(void){}

E_API int e_configure_registry_exists(const char *p){return !strcmp(p,"appearance/theme")||!strcmp(p,"appearance/wallpaper");}
E_API void e_configure_registry_call(const char *p,Evas_Object *parent EINA_UNUSED,const char *params EINA_UNUSED){printf("OPEN %s\n",p);fflush(stdout);}
E_API Eldbus_Service_Interface *e_msgbus_interface_attach(const Eldbus_Service_Interface_Desc *d){return eldbus_service_interface_register(connection,"/org/enlightenment/wm/RemoteObject",d);}
static Eina_Bool finish(void *data EINA_UNUSED){ecore_main_loop_quit();return ECORE_CALLBACK_CANCEL;}
int main(int argc,char **argv){
 if(argc!=2)return 2;
 ecore_init();edje_init();eldbus_init();configuration.desktop_backgrounds=eina_list_append(NULL,&configuration);connection=eldbus_connection_get(ELDBUS_CONNECTION_TYPE_SESSION);
 void *module=dlopen(argv[1],RTLD_NOW);if(!module){fprintf(stderr,"%s\n",dlerror());return 3;}
 void *(*init)(E_Module *)=dlsym(module,"e_modapi_init");int (*shutdown)(E_Module *)=dlsym(module,"e_modapi_shutdown");
 E_Module m={0};if(!init||!shutdown||!init(&m))return 4;
 printf("READY %s\n",eldbus_connection_unique_name_get(connection));fflush(stdout);
 ecore_timer_add(10,finish,NULL);ecore_main_loop_begin();shutdown(&m);dlclose(module);eldbus_connection_unref(connection);eldbus_shutdown();eina_stringshare_del(configuration.desktop_default_background);eina_list_free(configuration.desktop_backgrounds);edje_shutdown();ecore_shutdown();return 0;
}
