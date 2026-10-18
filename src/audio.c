/* SPDX-License-Identifier: GPL-3.0-only */
#include "audio.h"
#include <glib.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
static int frost_preview(void){const char *s=getenv("WORKSTATION_FROST_PREVIEW");return s&&!strcmp(s,"1");}
#include <math.h>
#include <stdint.h>

typedef struct {char *kind,*title,*name;unsigned id;double volume;int muted,selected,monitor,route;} Item;
typedef struct {char *action,*kind;unsigned id;int value;double previous;Eina_Bool armed;} Binding;
static Evas_Object *host,*scroller,*body,*controls;
static Elm_Theme *widget_theme;
static GPtrArray *items,*bindings;
static GQueue commands;
static Ecore_Exe *worker,*watcher;
static Ecore_Event_Handler *on_data,*on_exit;
static Ecore_Timer *refresh_timer;
static GString *reply;
static void (*report)(const char *);
static char *helper,*message;
static int tab,active,connected,syncing,dragging,dirty,writing,worker_snapshot;
static void render(void);
static void start_watch(void);
static void start_next(void);
static void schedule_refresh(void);
static void set_status(const char *text){g_free(message);message=g_strdup(text);if(active&&report)report(message);}
const char *audio_status(void){return message?message:"Connecting to your sound service…";}
static void free_item(void *data){Item *i=data;g_free(i->kind);g_free(i->title);g_free(i->name);g_free(i);}
static void free_binding(void *data){Binding *b=data;g_free(b->action);g_free(b->kind);g_free(b);}
static Binding *binding(const char *action,Item *i,int value){Binding *b=g_new0(Binding,1);b->action=g_strdup(action);b->kind=g_strdup(i->kind);b->id=i->id;b->value=value;b->previous=i->volume;g_ptr_array_add(bindings,b);return b;}
static void cc(Evas_Object *o,const char *name,int r,int g,int b,int a){if(!frost_preview())return;edje_object_color_class_set(elm_layout_edje_get(o),name,r,g,b,a,255,255,255,255,255,255,255,255);}
static void button_style(Evas_Object *o){if(!frost_preview())return;if(!strcmp(elm_object_widget_type_get(o),"Elm_Button")){elm_object_style_set(o,"frost-action");return;}cc(o,"/bg/normal/button",221,235,243,255);cc(o,"/bg/pressed/button",187,215,232,255);cc(o,"/fg/normal/button",38,58,73,255);cc(o,"/fg/pressed/button",26,45,60,255);cc(o,"/shadow/normal/button",0,0,0,30);}
static Evas_Object *label(Evas_Object *box,const char *text,int size){
 Evas_Object *o=elm_label_add(box);char *markup=frost_preview()?g_markup_printf_escaped("<color=#263a49><font_size=%d>%s</font_size></color>",size,text):g_markup_printf_escaped(size>=16?"<b>%s</b>":"%s",text);elm_object_text_set(o,markup);g_free(markup);
 evas_object_size_hint_weight_set(o,EVAS_HINT_EXPAND,0);evas_object_size_hint_align_set(o,0,0.5);elm_box_pack_end(box,o);evas_object_show(o);return o;
}
static Evas_Object *box_add(Evas_Object *parent,int horizontal){Evas_Object *box=elm_box_add(parent);elm_box_horizontal_set(box,horizontal);elm_box_padding_set(box,8,12);elm_box_align_set(box,0,0);evas_object_size_hint_weight_set(box,EVAS_HINT_EXPAND,0);evas_object_size_hint_align_set(box,EVAS_HINT_FILL,0);return box;}
static void pack(Evas_Object *box,Evas_Object *child){elm_box_pack_end(box,child);evas_object_show(child);}
static void request(const char *action,const char *kind,unsigned id,int value){
 if(!connected||syncing)return;
 char *args=g_strdup_printf("%s %s %u %d",action,kind,id,value);g_queue_push_tail(&commands,args);writing=1;
 if(controls)elm_object_disabled_set(controls,EINA_TRUE);
 set_status("Applying your sound setting…");start_next();
}
static void choose(void *data,Evas_Object *obj,void *event){(void)obj;(void)event;Binding *b=data;request(b->action,b->kind,b->id,b->value);}
static void muted(void *data,Evas_Object *obj,void *event){(void)event;Binding *b=data;if(!syncing)request("mute",b->kind,b->id,elm_check_state_get(obj)?1:0);}
static void armed(void *data,Evas *e,Evas_Object *o,void *event){(void)e;(void)o;(void)event;((Binding *)data)->armed=EINA_TRUE;}
static void mark_changed(void *data,Evas_Object *obj,void *event){(void)obj;(void)event;((Binding *)data)->armed=EINA_TRUE;}
static void drag_start(void *data,Evas_Object *obj,void *event){(void)obj;(void)event;((Binding *)data)->armed=EINA_TRUE;dragging=1;}
static void volume_changed(void *data,Evas_Object *obj,void *event){
 (void)event;Binding *b=data;if(syncing||!b->armed)return;int value=(int)lround(elm_slider_value_get(obj));
 b->armed=EINA_FALSE;dragging=0;if(fabs(value-b->previous)>=0.5)request("volume",b->kind,b->id,value);else if(dirty)render();
}
static Item *device(const char *kind,int id){for(unsigned n=0;n<items->len;n++){Item *i=g_ptr_array_index(items,n);if(!strcmp(i->kind,kind)&&(int)i->id==id)return i;}return NULL;}
static Evas_Object *picker(Evas_Object *box,Item *i,int routing){
 Evas_Object *pick=elm_hoversel_add(box);elm_hoversel_hover_parent_set(pick,host);
 const char *kind=routing?(!strcmp(i->kind,"playback")?"output":"input"):i->kind;
 Item *selected=routing?device(kind,i->route):i;elm_object_text_set(pick,selected?selected->title:"Choose a device");button_style(pick);elm_object_access_info_set(pick,routing?"Application audio device":"Default audio device");
 for(unsigned n=0;n<items->len;n++){
  Item *d=g_ptr_array_index(items,n);if(strcmp(d->kind,kind)||(!routing&&d->monitor&&!d->selected))continue;
  Binding *b=binding(routing?"route":"default",routing?i:d,(int)d->id);
  elm_hoversel_item_add(pick,d->title,NULL,ELM_ICON_NONE,choose,b);
 }
 evas_object_size_hint_weight_set(pick,0,0);evas_object_size_hint_align_set(pick,0,0.5);evas_object_size_hint_min_set(pick,350,34);evas_object_size_hint_max_set(pick,440,-1);pack(box,pick);return pick;
}
static void volume_controls(Evas_Object *box,Item *i){
 char text[100];snprintf(text,sizeof(text),"Volume — %.0f%%%s",i->volume,i->volume>100?" (above normal)":"");label(box,text,12);
 Evas_Object *row=box_add(box,1);pack(box,row);
 Evas_Object *slider=elm_slider_add(row);elm_slider_min_max_set(slider,0,100);elm_slider_span_size_set(slider,260);elm_slider_value_set(slider,fmin(100,i->volume));elm_slider_unit_format_set(slider,"");elm_slider_indicator_format_set(slider,"");elm_slider_indicator_show_set(slider,EINA_FALSE);
 cc(slider,"/bg/normal/slider/base",178,201,215,255);cc(slider,"/fg/normal/slider/bar",75,130,164,255);cc(slider,"/fg/normal/slider/text/units",38,58,73,255);elm_object_access_info_set(slider,"Volume, from zero to one hundred percent");
 evas_object_size_hint_weight_set(slider,EVAS_HINT_EXPAND,0);evas_object_size_hint_align_set(slider,EVAS_HINT_FILL,0.5);pack(row,slider);
 Binding *b=binding("volume",i,0);
 evas_object_event_callback_add(slider,EVAS_CALLBACK_MOUSE_DOWN,armed,b);evas_object_event_callback_add(slider,EVAS_CALLBACK_KEY_DOWN,armed,b);
 evas_object_smart_callback_add(slider,"changed",mark_changed,b);
 evas_object_smart_callback_add(slider,"slider,drag,start",drag_start,b);evas_object_smart_callback_add(slider,"slider,drag,stop",volume_changed,b);evas_object_smart_callback_add(slider,"delay,changed",volume_changed,b);
 Evas_Object *mute=elm_check_add(row);elm_check_state_set(mute,i->muted);elm_object_access_info_set(mute,"Mute this device or application");pack(row,mute);label(row,!strcmp(i->kind,"input")?"Mute microphone":!strcmp(i->kind,"output")?"Mute sound":"Mute app",12);evas_object_smart_callback_add(mute,"changed",muted,binding("mute",i,0));
}
static void refresh(void *data,Evas_Object *obj,void *event){(void)data;(void)obj;(void)event;start_watch();dirty=1;schedule_refresh();}
static void change_tab(void *data,Evas_Object *obj,void *event){(void)obj;(void)event;tab=(int)(intptr_t)data;render();}
static void render(void){
 if(!scroller||dragging||writing)return;
 syncing=1;
 if(body){elm_object_content_unset(scroller);evas_object_del(body);}g_ptr_array_set_size(bindings,0);
 body=box_add(scroller,0);evas_object_size_hint_min_set(body,650,0);
 Evas_Object *tabs=box_add(body,1);pack(body,tabs);
 const char *names[]={"Output","Microphone","Applications"};
 for(int t=0;t<3;t++){Evas_Object *button=elm_button_add(tabs);char text[64];snprintf(text,sizeof(text),"%s%s",t==tab?"• ":"",names[t]);elm_object_text_set(button,text);button_style(button);evas_object_smart_callback_add(button,"clicked",change_tab,(void *)(intptr_t)t);pack(tabs,button);}
 Evas_Object *again=elm_button_add(tabs);elm_object_text_set(again,"Refresh");button_style(again);evas_object_smart_callback_add(again,"clicked",refresh,NULL);pack(tabs,again);
 controls=box_add(body,0);pack(body,controls);elm_object_disabled_set(controls,!connected);
 if(!connected)label(controls,"Sound controls are unavailable. Check your sound service, then choose Refresh.",12);
 else if(tab<2){
  const char *kind=tab==0?"output":"input";Item *chosen=NULL;int count=0;
  for(unsigned n=0;n<items->len;n++){Item *i=g_ptr_array_index(items,n);if(strcmp(i->kind,kind)||i->monitor)continue;count++;if(i->selected)chosen=i;}
  if(!chosen)for(unsigned n=0;n<items->len;n++){Item *i=g_ptr_array_index(items,n);if(!strcmp(i->kind,kind)&&i->selected){chosen=i;break;}}
  label(controls,tab==0?"Play sound through":"Use this microphone",17);
  if(chosen){picker(controls,chosen,0);label(controls,"New apps use this device. Move an existing app under Applications.",11);volume_controls(controls,chosen);}
  else label(controls,count?"No default device is selected. Select an available device below.":"No available devices were reported.",12);
  if(!chosen&&count){for(unsigned n=0;n<items->len;n++){Item *i=g_ptr_array_index(items,n);if(!strcmp(i->kind,kind)&&!i->monitor){picker(controls,i,0);break;}}}
  label(controls,tab==0?"Muted sound stays muted until you turn it back on.":"Microphone mute controls this input; individual apps can also have their own mute.",11);
 }else{
  label(controls,"Applications using sound",17);int count=0;
  for(unsigned n=0;n<items->len;n++){
   Item *i=g_ptr_array_index(items,n);if(strcmp(i->kind,"playback")&&strcmp(i->kind,"recording"))continue;count++;
   Evas_Object *inner=box_add(controls,0);pack(controls,inner);label(inner,!strcmp(i->kind,"recording")?"Using a microphone":"Playing sound",11);
   label(inner,i->title,14);picker(inner,i,1);volume_controls(inner,i);
  }
  if(!count)label(controls,"No applications are currently playing or recording sound.",12);
 }
 elm_object_content_set(scroller,body);evas_object_show(body);syncing=0;
}
static void start_watch(void){if(!watcher)watcher=ecore_exe_pipe_run("env LC_ALL=C pactl subscribe",ECORE_EXE_PIPE_READ|ECORE_EXE_PIPE_READ_LINE_BUFFERED|ECORE_EXE_TERM_WITH_PARENT,NULL);}
static void start_next(void){
 if(worker||!helper)return;
 char *args=g_queue_pop_head(&commands);worker_snapshot=args==NULL;
 if(!args){if(!dirty||!active)return;args=g_strdup("snapshot");dirty=0;}
 char *quoted=g_shell_quote(helper),*command=g_strdup_printf("python3 %s %s",quoted,args);g_free(quoted);g_free(args);
 reply=g_string_new(NULL);worker=ecore_exe_pipe_run(command,ECORE_EXE_PIPE_READ|ECORE_EXE_TERM_WITH_PARENT,NULL);g_free(command);
 if(!worker){g_string_free(reply,TRUE);reply=NULL;connected=0;writing=0;set_status("Could not start the sound-service adapter.");render();}
}
static Eina_Bool delayed_refresh(void *data){(void)data;refresh_timer=NULL;start_next();return ECORE_CALLBACK_CANCEL;}
static void schedule_refresh(void){dirty=1;if(active&&!refresh_timer&&!worker)refresh_timer=ecore_timer_add(.25,delayed_refresh,NULL);}
static Eina_Bool data_event(void *data,int type,void *event){
 (void)data;(void)type;Ecore_Exe_Event_Data *e=event;
 if(e->exe==worker&&reply){if(reply->len+(size_t)e->size<1024*1024)g_string_append_len(reply,e->data,e->size);else ecore_exe_terminate(worker);}
 else if(e->exe==watcher&&e->lines)for(int n=0;e->lines[n].line;n++){
  const char *s=e->lines[n].line;if(strstr(s," on sink ")||strstr(s," on source ")||strstr(s," on sink-input ")||strstr(s," on source-output ")||strstr(s," on server "))schedule_refresh();
 }
 return ECORE_CALLBACK_PASS_ON;
}
static void parse_reply(int okay){
 GPtrArray *fresh=g_ptr_array_new_with_free_func(free_item);int ready=0,error=0;char **lines=g_strsplit(reply?reply->str:"","\n",-1);
 for(int n=0;lines[n];n++){
  char **fields=g_strsplit(lines[n],"\t",-1);unsigned count=g_strv_length(fields);
  for(unsigned f=0;f<count;f++){char *plain=g_uri_unescape_string(fields[f],NULL);if(plain){g_free(fields[f]);fields[f]=plain;}}
  if(count>=2&&!strcmp(fields[0],"error")){error=1;set_status(fields[1]);}
  else if(count>=2&&!strcmp(fields[0],"ready"))ready=1;
  else if(count>=2&&!strcmp(fields[0],"ok"))set_status(fields[1]);
  else if(count==10&&!strcmp(fields[0],"item")){
   Item *i=g_new0(Item,1);i->kind=g_strdup(fields[1]);i->id=(unsigned)g_ascii_strtoull(fields[2],NULL,10);i->title=g_strdup(fields[3]);i->volume=g_ascii_strtod(fields[4],NULL);i->muted=atoi(fields[5]);i->selected=atoi(fields[6]);i->monitor=atoi(fields[7]);i->route=atoi(fields[8]);i->name=g_strdup(fields[9]);g_ptr_array_add(fresh,i);
  }
  g_strfreev(fields);
 }
 g_strfreev(lines);
 if(worker_snapshot){connected=okay&&ready&&!error;if(connected){g_ptr_array_free(items,TRUE);items=fresh;fresh=NULL;if(!message||strstr(message,"Connecting")||strstr(message,"unavailable"))set_status("Live sound settings · changes apply when you use a control");}else if(!error)set_status("Unable to read sound settings. Choose Refresh to try again.");}
 else if(!okay&&!error)set_status("The sound setting was not changed. Refresh and try again.");
 if(fresh)g_ptr_array_free(fresh,TRUE);
}
static Eina_Bool exit_event(void *data,int type,void *event){
 (void)data;(void)type;Ecore_Exe_Event_Del *e=event;
 if(e->exe==watcher){watcher=NULL;connected=0;set_status("Sound service disconnected. Choose Refresh to reconnect.");render();}
 if(e->exe!=worker)return ECORE_CALLBACK_PASS_ON;
 parse_reply(e->exit_code==0);worker=NULL;g_string_free(reply,TRUE);reply=NULL;
 if(!g_queue_is_empty(&commands)){start_next();return ECORE_CALLBACK_PASS_ON;}
 if(writing){writing=0;dirty=1;start_next();}
 else {render();if(dirty)schedule_refresh();}
 return ECORE_CALLBACK_PASS_ON;
}
static void widgets_deleted(void *data,Evas *e,Evas_Object *o,void *event){(void)data;(void)e;(void)o;(void)event;scroller=NULL;body=NULL;controls=NULL;}
void audio_init(Evas_Object *parent,void (*status)(const char *)){
 host=parent;report=status;if(frost_preview()){widget_theme=elm_theme_new();elm_theme_set(widget_theme,"default");elm_theme_extension_add(widget_theme,getenv("WORKSTATION_THEME"));}helper=g_strdup(getenv("WORKSTATION_AUDIO_HELPER"));items=g_ptr_array_new_with_free_func(free_item);bindings=g_ptr_array_new_with_free_func(free_binding);g_queue_init(&commands);
 scroller=elm_scroller_add(parent);elm_object_theme_set(scroller,widget_theme);cc(scroller,"/bg/normal/scroller/base",0,0,0,0);cc(scroller,"/shadow/normal/scroller",0,0,0,0);evas_object_event_callback_add(scroller,EVAS_CALLBACK_DEL,widgets_deleted,NULL);elm_scroller_policy_set(scroller,ELM_SCROLLER_POLICY_OFF,ELM_SCROLLER_POLICY_AUTO);elm_scroller_content_min_limit(scroller,EINA_FALSE,EINA_FALSE);elm_object_part_content_set(parent,"audio.content",scroller);evas_object_show(scroller);
 on_data=ecore_event_handler_add(ECORE_EXE_EVENT_DATA,data_event,NULL);on_exit=ecore_event_handler_add(ECORE_EXE_EVENT_DEL,exit_event,NULL);set_status("Connecting to your sound service…");render();
}
void audio_visible(Eina_Bool visible){int was=active;active=visible;if(visible){if(!was){start_watch();schedule_refresh();}if(report)report(audio_status());}}
char *audio_diagnostics(void){GString *s=g_string_new("Live audio devices and streams\n");for(unsigned n=0;n<items->len;n++){Item *i=g_ptr_array_index(items,n);g_string_append_printf(s,"%s: %s\n  %s  %.0f%%  %s%s\n",i->kind,i->title,i->name,i->volume,i->muted?"muted":"sound enabled",i->selected?" / default":"");}return g_string_free(s,FALSE);}
void audio_shutdown(void){if(refresh_timer)ecore_timer_del(refresh_timer);if(on_data)ecore_event_handler_del(on_data);if(on_exit)ecore_event_handler_del(on_exit);if(worker)ecore_exe_terminate(worker);if(watcher)ecore_exe_terminate(watcher);if(reply)g_string_free(reply,TRUE);if(scroller)evas_object_del(scroller);g_queue_clear_full(&commands,g_free);g_ptr_array_free(items,TRUE);g_ptr_array_free(bindings,TRUE);g_free(helper);g_free(message);if(widget_theme)elm_theme_free(widget_theme);}
