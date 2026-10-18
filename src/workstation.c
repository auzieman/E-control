/* SPDX-License-Identifier: GPL-3.0-only */
#include "workstation.h"
#include <glib.h>
#include <stdlib.h>
#include <string.h>
typedef struct { char *op,*target; } Action;
typedef struct { char *key,*kind; Evas_Object *object; } Field;
static Evas_Object *scroller,*body,*host;
static GPtrArray *actions,*fields;
static Ecore_Exe *worker;
static Ecore_Event_Handler *data_handler,*exit_handler;
static GString *reply;
static char *provider,*page;
static int current=-1,worker_page=-1,rendering=0;
static void (*report)(const char *);
static void request(const char *,const char *);
static void field_free(void *p){Field *f=p;g_free(f->key);g_free(f->kind);g_free(f);}
static void action_free(void *p){Action *a=p;g_free(a->op);g_free(a->target);g_free(a);}
static void pack(Evas_Object *b,Evas_Object *o){elm_box_pack_end(b,o);evas_object_show(o);}
static Evas_Object *box(Evas_Object *parent,int horizontal){Evas_Object *b=elm_box_add(parent);elm_box_horizontal_set(b,horizontal);elm_box_padding_set(b,8,8);evas_object_size_hint_weight_set(b,EVAS_HINT_EXPAND,0);evas_object_size_hint_align_set(b,EVAS_HINT_FILL,0);elm_box_align_set(b,0,0);return b;}
static Evas_Object *region(Evas_Object *b,Evas_Object *o,int w,int h){
 Evas_Object *t=elm_table_add(b),*spacer=evas_object_rectangle_add(evas_object_evas_get(b));
 evas_object_color_set(spacer,0,0,0,0);evas_object_size_hint_min_set(spacer,w,h);
 elm_table_pack(t,spacer,0,0,1,1);evas_object_show(spacer);
 evas_object_size_hint_weight_set(o,EVAS_HINT_EXPAND,EVAS_HINT_EXPAND);evas_object_size_hint_align_set(o,EVAS_HINT_FILL,EVAS_HINT_FILL);
 elm_table_pack(t,o,0,0,1,1);evas_object_show(o);
 evas_object_size_hint_weight_set(t,EVAS_HINT_EXPAND,0);evas_object_size_hint_align_set(t,EVAS_HINT_FILL,0);pack(b,t);return spacer;
}
static void label(Evas_Object *b,const char *s,int heading){Evas_Object *o=elm_label_add(b);char *m=g_markup_printf_escaped(heading?"<align=left><b>%s</b></align>":"<align=left>%s</align>",s);elm_object_text_set(o,m);g_free(m);elm_label_line_wrap_set(o,ELM_WRAP_WORD);elm_label_wrap_width_set(o,640);evas_object_size_hint_weight_set(o,EVAS_HINT_EXPAND,0);evas_object_size_hint_align_set(o,EVAS_HINT_FILL,.5);pack(b,o);}
static void clicked(void *d,Evas_Object *o,void *e){(void)o;(void)e;if(worker||rendering)return;Action *a=d;if(!strcmp(a->op,"view")){g_free(page);page=g_strdup(a->target);}request(a->op,a->target);}
static void button(Evas_Object *b,const char *name,const char *op,const char *target){Action *a=g_new0(Action,1);a->op=g_strdup(op);a->target=g_strdup(target);g_ptr_array_add(actions,a);Evas_Object *o=elm_button_add(b);char *m=elm_entry_utf8_to_markup(name);elm_object_text_set(o,m);free(m);evas_object_smart_callback_add(o,"clicked",clicked,a);pack(b,o);}
static void quote(GString *s,const char *v){g_string_append_c(s,'"');for(const unsigned char *p=(const unsigned char *)v;*p;p++){if(*p=='"'||*p=='\\'){g_string_append_c(s,'\\');g_string_append_c(s,*p);}else if(*p<32)g_string_append_printf(s,"\\u%04x",*p);else g_string_append_c(s,*p);}g_string_append_c(s,'"');}
static void wipe(char *p,size_t n){volatile char *v=p;while(n--)*v++=0;}
static void request(const char *op,const char *target){
 if(worker)return;
 GString *s=g_string_new("{\"op\":");quote(s,op);g_string_append(s,",\"target\":");quote(s,target);g_string_append(s,",\"values\":{");
 for(unsigned n=0;n<fields->len&&strcmp(op,"view")&&strcmp(op,"launch")&&!g_str_has_suffix(op,"_form");n++){Field *f=g_ptr_array_index(fields,n);if(n)g_string_append_c(s,',');quote(s,f->key);g_string_append_c(s,':');char *v=!strcmp(f->kind,"check")?strdup(elm_check_state_get(f->object)?"1":"0"):elm_entry_markup_to_utf8(elm_entry_entry_get(f->object));quote(s,v?v:"");if(v){wipe(v,strlen(v));free(v);}if(!strcmp(f->kind,"password"))elm_entry_entry_set(f->object,"");}
 g_string_append(s,"}}");char *p=g_shell_quote(provider),*cmd=g_strdup_printf("python3 %s",p);g_free(p);reply=g_string_new(NULL);
 worker=ecore_exe_pipe_run(cmd,ECORE_EXE_PIPE_READ|ECORE_EXE_PIPE_WRITE|ECORE_EXE_TERM_WITH_PARENT,NULL);g_free(cmd);worker_page=current;
 if(worker){ecore_exe_send(worker,s->str,(int)s->len);ecore_exe_close_stdin(worker);elm_object_disabled_set(body,EINA_TRUE);report("Working…");}
 else{g_string_free(reply,TRUE);reply=NULL;report("Could not start the workstation provider.");}
 wipe(s->str,s->len);g_string_free(s,TRUE);
}
static void free_preview_theme(void *data,Evas *e EINA_UNUSED,Evas_Object *o EINA_UNUSED,void *event EINA_UNUSED){elm_theme_free(data);}
static void theme_preview(Evas_Object *parent,const char *file){
 Elm_Theme *theme=elm_theme_new();elm_theme_set(theme,file);
 Evas_Object *frame=elm_frame_add(parent);elm_object_theme_set(frame,theme);elm_object_text_set(frame,"Example application window");
 evas_object_event_callback_add(frame,EVAS_CALLBACK_DEL,free_preview_theme,theme);
 Evas_Object *content=box(frame,0);elm_object_theme_set(content,theme);
 Evas_Object *sample=elm_label_add(content);elm_object_theme_set(sample,theme);elm_object_text_set(sample,"<b>Documents</b> — Aa Bb Cc 0123456789");pack(content,sample);
 Evas_Object *row=box(content,1);pack(content,row);
 Evas_Object *btn=elm_button_add(row);elm_object_theme_set(btn,theme);elm_object_text_set(btn,"Open folder");pack(row,btn);
 Evas_Object *check=elm_check_add(row);elm_object_theme_set(check,theme);elm_object_text_set(check,"Show hidden files");elm_check_state_set(check,EINA_TRUE);pack(row,check);
 Evas_Object *slider=elm_slider_add(content);elm_object_theme_set(slider,theme);elm_slider_value_set(slider,.65);evas_object_size_hint_min_set(slider,400,32);pack(content,slider);
 Evas_Object *entry=elm_entry_add(content);elm_object_theme_set(entry,theme);elm_entry_single_line_set(entry,EINA_TRUE);elm_entry_entry_set(entry,"Search documents…");evas_object_size_hint_weight_set(entry,EVAS_HINT_EXPAND,0);evas_object_size_hint_align_set(entry,EVAS_HINT_FILL,0);pack(content,entry);
 Evas_Object *progress=elm_progressbar_add(content);elm_object_theme_set(progress,theme);elm_object_text_set(progress,"Copying files");elm_progressbar_value_set(progress,.6);evas_object_size_hint_weight_set(progress,EVAS_HINT_EXPAND,0);evas_object_size_hint_align_set(progress,EVAS_HINT_FILL,0);pack(content,progress);
 elm_object_content_set(frame,content);evas_object_show(content);region(parent,frame,560,220);
}
static void render(const char *response){
 rendering=1;
 if(body){elm_object_content_unset(scroller);evas_object_del(body);}g_ptr_array_set_size(actions,0);g_ptr_array_set_size(fields,0);
 body=box(scroller,0);evas_object_size_hint_min_set(body,650,0);
 Evas_Object *tabs=box(body,1);pack(body,tabs);
 if(current==3){const char *names[]={"Wired","Wireless","Bluetooth","Firewall","VPN"};const char *ids[]={"wired","wifi","bluetooth","firewall","vpn"};for(int i=0;i<5;i++)button(tabs,names[i],"view",ids[i]);}
 if(current==0){const char *names[]={"Theme","Wallpaper","Text & size","Panels","Advanced"};const char *ids[]={"appearance","appearance-wallpaper","appearance-text","appearance-layout","appearance-advanced"};for(int i=0;i<5;i++)button(tabs,names[i],"view",ids[i]);}
 button(tabs,"Refresh","view",page?page:"wired");
 char **lines=g_strsplit(response?response:"","\n",-1);Evas_Object *row=NULL,*choices=NULL;Elm_Object_Item *selected_item=NULL;int row_count=0;
 for(int n=0;lines[n];n++){
  char **f=g_strsplit(lines[n],"\t",-1);int count=g_strv_length(f);
  for(int i=0;i<count;i++){char *v=g_uri_unescape_string(f[i],NULL);if(v){g_free(f[i]);f[i]=v;}}
  if(count==2&&(!strcmp(f[0],"heading")||!strcmp(f[0],"text"))){row=NULL;label(body,f[1],!strcmp(f[0],"heading"));}
  else if(count==3&&!strcmp(f[0],"meter")){
   row=NULL;Evas_Object *meter=elm_progressbar_add(body);elm_object_text_set(meter,f[1]);elm_progressbar_unit_format_set(meter,"%.0f %%");elm_progressbar_value_set(meter,g_ascii_strtod(f[2],NULL));evas_object_size_hint_weight_set(meter,EVAS_HINT_EXPAND,0);evas_object_size_hint_align_set(meter,EVAS_HINT_FILL,0);pack(body,meter);
  }
  else if(count==2&&!strcmp(f[0],"theme_preview")){row=NULL;theme_preview(body,f[1]);}
  else if(count==3&&!strcmp(f[0],"preview")){
   row=NULL;Evas_Object *o=NULL;
   if(g_str_has_suffix(f[1],".edj")){
    o=edje_object_add(evas_object_evas_get(body));
    if(!edje_object_file_set(o,f[1],f[2])){evas_object_del(o);o=NULL;}
    else{edje_object_animation_set(o,EINA_FALSE);edje_object_play_set(o,EINA_FALSE);}
   }else{o=elm_image_add(body);if(!elm_image_file_set(o,f[1],NULL)){evas_object_del(o);o=NULL;}}
   if(o){Evas_Object *clip=region(body,o,560,200);evas_object_color_set(clip,255,255,255,255);evas_object_pass_events_set(clip,EINA_TRUE);evas_object_clip_set(o,clip);}
   else label(body,"Preview unavailable for this wallpaper.",0);
  }
  else if(count==4&&(!strcmp(f[0],"choice")||!strcmp(f[0],"selected_choice"))){
   if(!choices){choices=elm_list_add(body);elm_list_mode_set(choices,ELM_LIST_SCROLL);region(body,choices,560,150);}
   Action *a=g_new0(Action,1);a->op=g_strdup(f[2]);a->target=g_strdup(f[3]);g_ptr_array_add(actions,a);
   char *m=elm_entry_utf8_to_markup(f[1]);Elm_Object_Item *item=elm_list_item_append(choices,m,NULL,NULL,clicked,a);free(m);if(!strcmp(f[0],"selected_choice")){elm_list_item_selected_set(item,EINA_TRUE);selected_item=item;}
  }
  else if(count==4&&!strcmp(f[0],"action")){if(!row||row_count>=2){row=box(body,1);pack(body,row);row_count=0;}button(row,f[1],f[2],f[3]);row_count++;}
  else if(count==5&&!strcmp(f[0],"field")){
   row=NULL;Field *v=g_new0(Field,1);v->key=g_strdup(f[1]);v->kind=g_strdup(f[4]);
   if(!strcmp(f[4],"check")){v->object=elm_check_add(body);elm_object_text_set(v->object,f[2]);elm_check_state_set(v->object,!strcmp(f[3],"1"));}
   else{label(body,f[2],0);v->object=elm_entry_add(body);elm_entry_single_line_set(v->object,EINA_TRUE);elm_entry_scrollable_set(v->object,EINA_TRUE);elm_entry_password_set(v->object,!strcmp(f[4],"password"));elm_entry_prediction_allow_set(v->object,EINA_FALSE);char *m=elm_entry_utf8_to_markup(f[3]);elm_entry_entry_set(v->object,m);free(m);evas_object_size_hint_min_set(v->object,440,34);}
   evas_object_size_hint_weight_set(v->object,EVAS_HINT_EXPAND,0);evas_object_size_hint_align_set(v->object,EVAS_HINT_FILL,.5);pack(body,v->object);g_ptr_array_add(fields,v);
  }
  g_strfreev(f);
 }
 if(choices){elm_list_go(choices);if(selected_item)elm_list_item_show(selected_item);}
 g_strfreev(lines);elm_object_content_set(scroller,body);evas_object_show(body);elm_scroller_region_show(scroller,0,0,1,1);rendering=0;
}
static Eina_Bool data_event(void *d,int t,void *event){(void)d;(void)t;Ecore_Exe_Event_Data *e=event;if(e->exe==worker&&reply){if(reply->len+e->size<2*1024*1024)g_string_append_len(reply,e->data,e->size);else ecore_exe_terminate(worker);}return ECORE_CALLBACK_PASS_ON;}
static Eina_Bool exit_event(void *d,int t,void *event){(void)d;(void)t;Ecore_Exe_Event_Del *e=event;if(e->exe!=worker)return ECORE_CALLBACK_PASS_ON;worker=NULL;
 if(worker_page==current){
  char **lines=g_strsplit(reply->str,"\n",-1);char *msg=NULL;int ready=0;
  for(int n=0;lines[n];n++){if(!strcmp(lines[n],"ready"))ready=1;else if(g_str_has_prefix(lines[n],"error\t")||g_str_has_prefix(lines[n],"notice\t")){g_free(msg);msg=g_uri_unescape_string(strchr(lines[n],'\t')+1,NULL);}}
  if(!e->exit_code&&ready)render(reply->str);
  if(body){elm_object_disabled_set(body,EINA_FALSE);}
  report(msg?msg:e->exit_code?"Operation failed. Review the form and try again.":"Current system state loaded.");g_free(msg);g_strfreev(lines);
 }
 g_string_free(reply,TRUE);reply=NULL;
 if(worker_page!=current&&current>=0)request("view",page);
 return ECORE_CALLBACK_PASS_ON;
}
void workstation_init(Evas_Object *p,void (*cb)(const char *)){
 host=p;report=cb;actions=g_ptr_array_new_with_free_func(action_free);fields=g_ptr_array_new_with_free_func(field_free);
 const char *base=getenv("WORKSTATION_SETTINGS_PROVIDER"),*override=getenv("WORKSTATION_WORKSTATION_PROVIDER");char *dir=base?g_path_get_dirname(base):g_strdup(".");provider=override?g_strdup(override):g_build_filename(dir,"workstation-provider.py",NULL);g_free(dir);
 scroller=elm_scroller_add(host);elm_scroller_policy_set(scroller,ELM_SCROLLER_POLICY_OFF,ELM_SCROLLER_POLICY_AUTO);elm_object_part_content_set(host,"network.content",scroller);evas_object_show(scroller);
 data_handler=ecore_event_handler_add(ECORE_EXE_EVENT_DATA,data_event,NULL);exit_handler=ecore_event_handler_add(ECORE_EXE_EVENT_DEL,exit_event,NULL);
}
void workstation_show(int p){if(p==current)return;current=p;if(p<0)return;const char *ids[]={"appearance","","","wired","","software","storage","printing","system","services"};g_free(page);page=g_strdup(ids[p]);render("text\tLoading current system state…\n");if(!worker)request("view",page);}
void workstation_shutdown(void){if(worker)ecore_exe_terminate(worker);if(data_handler)ecore_event_handler_del(data_handler);if(exit_handler)ecore_event_handler_del(exit_handler);g_ptr_array_free(actions,TRUE);g_ptr_array_free(fields,TRUE);if(reply)g_string_free(reply,TRUE);g_free(provider);g_free(page);}
