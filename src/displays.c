/* SPDX-License-Identifier: GPL-3.0-only */
#include "displays.h"
#include <glib.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
static int frost_preview(void){const char *s=getenv("WORKSTATION_FROST_PREVIEW");return s&&!strcmp(s,"1");}
#include <stdio.h>
#include <math.h>

typedef struct {char *name,*mode,**modes;int x,y,primary;Evas_Object *picker,*xs,*ys;} Output;
typedef struct {Output *output;char *mode;} Choice;
static Evas_Object *host,*scroll,*body,*edit,*keep,*revert,*notice,*decision_row,*try_button;
typedef struct {Output *output;Evas_Object *rect,*text,*hit;int start_x,start_y,ox,oy,rx,ry,tx,ty,hx,hy,width,height,down;} Drag;
static GPtrArray *outputs,*choices,*drags;
static Ecore_Exe *worker;
static Ecore_Event_Handler *data_handler,*exit_handler;
static Ecore_Timer *timer;
static GString *reply;
static char *helper,*message,*result;
static void (*report)(const char *);
static int active,supported,trial,pending,remaining,fine;
static Elm_Theme *widget_theme;
static void render(void);
static void read_state(void);
static void status(const char *text){g_free(message);message=g_strdup(text);if(active&&report)report(message);}
const char *displays_status(void){return message?message:"Reading displays…";}
static void output_free(void *data){Output *o=data;g_free(o->name);g_free(o->mode);g_strfreev(o->modes);g_free(o);}
static void choice_free(void *data){Choice *c=data;g_free(c->mode);g_free(c);}
static Evas_Object *box(Evas_Object *parent,int horizontal){Evas_Object *b=elm_box_add(parent);elm_box_horizontal_set(b,horizontal);elm_box_padding_set(b,10,10);elm_box_align_set(b,0,0);evas_object_size_hint_weight_set(b,EVAS_HINT_EXPAND,0);evas_object_size_hint_align_set(b,EVAS_HINT_FILL,0);return b;}
static void pack(Evas_Object *b,Evas_Object *o){elm_box_pack_end(b,o);evas_object_show(o);}
static Evas_Object *label(Evas_Object *b,const char *s){Evas_Object *o=elm_label_add(b);char *m=frost_preview()?g_markup_printf_escaped("<color=#263a49><font_size=13>%s</font_size></color>",s):g_markup_escape_text(s,-1);elm_object_text_set(o,m);g_free(m);evas_object_size_hint_align_set(o,0,.5);pack(b,o);return o;}
static void button_style(Evas_Object *o){if(!frost_preview())return;if(!strcmp(elm_object_widget_type_get(o),"Elm_Button"))elm_object_style_set(o,"frost-action");}
static Evas_Object *button(Evas_Object *b,const char *s,Evas_Smart_Cb cb,void *data){Evas_Object *o=elm_button_add(b);elm_object_text_set(o,s);button_style(o);if(cb)evas_object_smart_callback_add(o,"clicked",cb,data);pack(b,o);return o;}
static void choose(void *data,Evas_Object *obj,void *event){(void)obj;(void)event;Choice *c=data;g_free(c->output->mode);c->output->mode=g_strdup(c->mode);elm_object_text_set(c->output->picker,c->mode?c->mode:"Off");render();status("Resolution staged. Use Extend to fit screens, then Try changes.");}
static void position(void *data,Evas_Object *obj,void *event){(void)obj;(void)event;Output *o=data;o->x=(int)elm_spinner_value_get(o->xs);o->y=(int)elm_spinner_value_get(o->ys);status("Changes are staged. Choose Try changes when ready.");}
static void arrange(void *data,Evas_Object *obj,void *event){(void)obj;(void)event;int arrangement=(int)(intptr_t)data,mirror=arrangement==1,x=0;char *common=NULL;
 if(mirror&&outputs->len){Output *first=g_ptr_array_index(outputs,0);for(int n=0;first->modes[n];n++){int found=1;for(unsigned j=1;j<outputs->len;j++){Output *o=g_ptr_array_index(outputs,j);int has=0;for(int k=0;o->modes[k];k++)if(!strcmp(first->modes[n],o->modes[k]))has=1;if(!has)found=0;}if(found){common=g_strdup(first->modes[n]);break;}}if(!common){status("These displays have no shared resolution to mirror.");return;}}
 for(unsigned n=0;n<outputs->len;n++){Output *o=g_ptr_array_index(outputs,n);if(mirror){g_free(o->mode);o->mode=g_strdup(common);}else if(!o->mode&&o->modes[0])o->mode=g_strdup(o->modes[0]);o->x=(mirror||arrangement==3)?0:x;o->y=arrangement==3?x:0;int w=0,h=0;if(o->mode)sscanf(o->mode,"%dx%d",&w,&h);x+=arrangement==3?h:w;}
 if(arrangement==2&&outputs->len==2){Output *a=g_ptr_array_index(outputs,0),*b=g_ptr_array_index(outputs,1);int w=0,h=0;if(b->mode)sscanf(b->mode,"%dx%d",&w,&h);a->x=w;b->x=0;}
 g_free(common);render();status(mirror?"Mirror layout staged. Choose Try changes.":"Side-by-side layout staged. Adjust positions if needed, then try changes.");
}
static void fine_changed(void *data,Evas_Object *obj,void *event){(void)data;(void)event;fine=elm_check_state_get(obj);render();}
static void drag_down(void *data,Evas *e,Evas_Object *obj,void *event){
 (void)e;(void)obj;Drag *d=data;Evas_Event_Mouse_Down *m=event;if(m->button!=1||worker)return;
 d->down=1;d->start_x=m->canvas.x;d->start_y=m->canvas.y;d->ox=d->output->x;d->oy=d->output->y;
 evas_object_geometry_get(d->rect,&d->rx,&d->ry,&d->width,&d->height);
 evas_object_geometry_get(d->text,&d->tx,&d->ty,NULL,NULL);evas_object_geometry_get(d->hit,&d->hx,&d->hy,NULL,NULL);
 elm_object_scroll_freeze_push(scroll);m->event_flags|=EVAS_EVENT_FLAG_ON_HOLD;
}
static void drag_move(void *data,Evas *e,Evas_Object *obj,void *event){
 (void)e;(void)obj;Drag *d=data;Evas_Event_Mouse_Move *m=event;if(!d->down)return;
 int dx=m->cur.canvas.x-d->start_x,dy=m->cur.canvas.y-d->start_y;
 evas_object_move(d->rect,d->rx+dx,d->ry+dy);evas_object_move(d->text,d->tx+dx,d->ty+dy);evas_object_move(d->hit,d->hx+dx,d->hy+dy);
 m->event_flags|=EVAS_EVENT_FLAG_ON_HOLD;
}
static void drag_up(void *data,Evas *e,Evas_Object *obj,void *event){
 (void)e;(void)obj;Drag *d=data;Evas_Event_Mouse_Up *m=event;if(!d->down||m->button!=1)return;d->down=0;
 elm_object_scroll_freeze_pop(scroll);
 int w=0,h=0;sscanf(d->output->mode,"%dx%d",&w,&h);int dx=m->canvas.x-d->start_x,dy=m->canvas.y-d->start_y;if(abs(dx)+abs(dy)<3)return;
 d->output->x=d->ox+(d->width?dx*w/d->width:0);d->output->y=d->oy+(d->height?dy*h/d->height:0);
 for(unsigned n=0;n<outputs->len;n++){
  Output *o=g_ptr_array_index(outputs,n);if(o==d->output||!o->mode)continue;
  int ow=0,oh=0;sscanf(o->mode,"%dx%d",&ow,&oh);int xs[]={o->x,o->x+ow,o->x-w},ys[]={o->y,o->y+oh,o->y-h};
  for(int k=0;k<3;k++){if(abs(d->output->x-xs[k])<30)d->output->x=xs[k];if(abs(d->output->y-ys[k])<30)d->output->y=ys[k];}
 }
 int minx=0,miny=0;
 for(unsigned n=0;n<outputs->len;n++){Output *o=g_ptr_array_index(outputs,n);if(!o->mode)continue;if(o->x<minx)minx=o->x;if(o->y<miny)miny=o->y;}
 for(unsigned n=0;n<outputs->len;n++){Output *o=g_ptr_array_index(outputs,n);if(o->mode){o->x-=minx;o->y-=miny;}}
 m->event_flags|=EVAS_EVENT_FLAG_ON_HOLD;render();status("Screen position staged. Choose Try changes when ready.");
}
static void diagram(Evas_Object *parent){
 int width=1,height=1;for(unsigned n=0;n<outputs->len;n++){Output *o=g_ptr_array_index(outputs,n);int w=0,h=0;if(o->mode){sscanf(o->mode,"%dx%d",&w,&h);if(o->x+w>width)width=o->x+w;if(o->y+h>height)height=o->y+h;}}
 Evas_Object *table=elm_table_add(parent);elm_table_homogeneous_set(table,EINA_TRUE);evas_object_size_hint_min_set(table,480,110);evas_object_size_hint_align_set(table,0,.5);pack(parent,table);
 for(unsigned n=0;n<outputs->len;n++){Output *o=g_ptr_array_index(outputs,n);if(!o->mode)continue;int duplicate=0;for(unsigned j=0;j<n;j++){Output *previous=g_ptr_array_index(outputs,j);if(previous->x==o->x&&previous->y==o->y&&!g_strcmp0(previous->mode,o->mode))duplicate=1;}if(duplicate)continue;int w=0,h=0;sscanf(o->mode,"%dx%d",&w,&h);int x=o->x*100/width,y=o->y*20/height,cw=w*100/width,ch=h*20/height;if(cw<1)cw=1;if(ch<1)ch=1;Evas_Object *rect=evas_object_rectangle_add(evas_object_evas_get(table));evas_object_color_set(rect,n%2?177:198,n%2?205:222,234,255);double scale=fmin(480.0/width,100.0/height);evas_object_size_hint_min_set(rect,(int)(w*scale),(int)(h*scale));evas_object_size_hint_weight_set(rect,EVAS_HINT_EXPAND,EVAS_HINT_EXPAND);evas_object_size_hint_align_set(rect,EVAS_HINT_FILL,EVAS_HINT_FILL);elm_table_pack(table,rect,x,y,cw,ch);evas_object_show(rect);Evas_Object *text=elm_label_add(table);GString *names=g_string_new(NULL);g_string_append_printf(names,"%u",n+1);int mirrored=0;for(unsigned j=n+1;j<outputs->len;j++){Output *other=g_ptr_array_index(outputs,j);if(other->x==o->x&&other->y==o->y&&!g_strcmp0(other->mode,o->mode)){g_string_append_printf(names," + %u",j+1);mirrored=1;}}char *s=g_strdup_printf("<color=#263a49><font_size=14>%s%s</font_size></color>",names->str,mirrored?" · Mirrored":o->primary?" · Main":"");elm_object_text_set(text,s);g_free(s);g_string_free(names,TRUE);elm_table_pack(table,text,x,y,cw,ch);evas_object_show(text);
 if(!mirrored){Drag *d=g_new0(Drag,1);d->output=o;d->rect=rect;d->text=text;d->hit=evas_object_rectangle_add(evas_object_evas_get(table));evas_object_color_set(d->hit,0,0,0,0);evas_object_size_hint_weight_set(d->hit,EVAS_HINT_EXPAND,EVAS_HINT_EXPAND);evas_object_size_hint_align_set(d->hit,EVAS_HINT_FILL,EVAS_HINT_FILL);elm_table_pack(table,d->hit,x,y,cw,ch);evas_object_event_callback_add(d->hit,EVAS_CALLBACK_MOUSE_DOWN,drag_down,d);evas_object_event_callback_add(d->hit,EVAS_CALLBACK_MOUSE_MOVE,drag_move,d);evas_object_event_callback_add(d->hit,EVAS_CALLBACK_MOUSE_UP,drag_up,d);evas_object_show(d->hit);g_ptr_array_add(drags,d);}}
}
static void refresh(void *data,Evas_Object *obj,void *event){(void)data;(void)obj;(void)event;g_clear_pointer(&result,g_free);read_state();}
static void finish(void *data,Evas_Object *obj,void *event){(void)obj;(void)event;if(worker&&pending){const char *s=data;ecore_exe_send(worker,s,(int)strlen(s));pending=0;elm_object_disabled_set(keep,EINA_TRUE);elm_object_disabled_set(revert,EINA_TRUE);status("Checking display settings…");}}
static Eina_Bool tick(void *data){(void)data;if(!pending){timer=NULL;return ECORE_CALLBACK_CANCEL;}char s[100];snprintf(s,sizeof(s),"Can you see everything? Reverting in %d seconds.",--remaining);status(s);if(notice)elm_object_text_set(notice,s);if(remaining<=0){finish("revert\n",NULL,NULL);timer=NULL;return ECORE_CALLBACK_CANCEL;}return ECORE_CALLBACK_RENEW;}
static void apply(void *data,Evas_Object *obj,void *event){(void)data;(void)obj;(void)event;if(worker||!supported||!outputs->len)return;g_clear_pointer(&result,g_free);
 GString *plan=g_string_new("[");for(unsigned n=0;n<outputs->len;n++){Output *o=g_ptr_array_index(outputs,n);char *name=g_strescape(o->name,NULL);g_string_append_printf(plan,"%s{\"name\":\"%s\",\"mode\":",n?",":"",name);g_free(name);if(o->mode)g_string_append_printf(plan,"\"%s\"",o->mode);else g_string_append(plan,"null");g_string_append_printf(plan,",\"x\":%d,\"y\":%d,\"primary\":%s}",o->x,o->y,o->primary?"true":"false");}g_string_append(plan,"]");char *q=g_shell_quote(helper),*p=g_shell_quote(plan->str),*cmd=g_strdup_printf("python3 %s trial %s",q,p);g_free(q);g_free(p);g_string_free(plan,TRUE);reply=g_string_new(NULL);trial=1;
 /* No TERM_WITH_PARENT: watchdog must survive a disappearing frontend. */
 worker=ecore_exe_pipe_run(cmd,ECORE_EXE_PIPE_READ|ECORE_EXE_PIPE_READ_LINE_BUFFERED|ECORE_EXE_PIPE_WRITE,NULL);g_free(cmd);if(!worker){g_string_free(reply,TRUE);reply=NULL;status("Could not start the display safety watchdog.");return;}elm_object_disabled_set(edit,EINA_TRUE);elm_object_disabled_set(try_button,EINA_TRUE);status("Trying display settings. They will revert unless you confirm.");
}
static void render(void){if(!scroll||pending)return;if(body){elm_object_content_unset(scroll);evas_object_del(body);}g_ptr_array_set_size(choices,0);g_ptr_array_set_size(drags,0);body=box(scroll,0);evas_object_size_hint_min_set(body,650,0);
 Evas_Object *row=box(body,1);pack(body,row);button(row,"Refresh displays",refresh,NULL);try_button=button(row,"Try changes — 15-second safety check",apply,NULL);elm_object_disabled_set(try_button,!supported||!outputs->len);
 notice=label(body,result?result:"Try a layout for 15 seconds. If it is unreadable, wait and it will revert.");decision_row=box(body,1);pack(body,decision_row);keep=elm_button_add(decision_row);elm_object_text_set(keep,"Keep these settings");button_style(keep);evas_object_smart_callback_add(keep,"clicked",finish,"keep\n");revert=elm_button_add(decision_row);elm_object_text_set(revert,"Revert now");button_style(revert);evas_object_smart_callback_add(revert,"clicked",finish,"revert\n");
 edit=box(body,0);pack(body,edit);row=box(edit,1);pack(edit,row);button(row,"Extend side by side",arrange,(void *)0);button(row,"Mirror screens",arrange,(void *)1);button(row,"Stack screens",arrange,(void *)3);if(outputs->len==2)button(row,"Swap sides",arrange,(void *)2);
 label(edit,"Drag screens to match your desk. To separate mirrored screens, choose Extend.");diagram(edit);
 Evas_Object *toggle=elm_check_add(edit);elm_object_text_set(toggle,"");elm_check_state_set(toggle,fine);Evas_Object *toggle_row=box(edit,1);pack(edit,toggle_row);pack(toggle_row,toggle);label(toggle_row,"Fine-tune positions");evas_object_smart_callback_add(toggle,"changed",fine_changed,NULL);
 for(unsigned n=0;n<outputs->len;n++){Output *o=g_ptr_array_index(outputs,n);char title[180];snprintf(title,sizeof(title),"%u · %s%s",n+1,!strncmp(o->name,"eDP",3)?"Laptop display":o->name,o->primary?" (main screen)":"");label(edit,title);row=box(edit,1);pack(edit,row);o->picker=elm_hoversel_add(row);elm_hoversel_hover_parent_set(o->picker,host);elm_object_text_set(o->picker,o->mode?o->mode:"Off");button_style(o->picker);evas_object_size_hint_min_set(o->picker,180,32);pack(row,o->picker);
 for(int k=-1;k<0||o->modes[k];k++){Choice *c=g_new0(Choice,1);c->output=o;c->mode=k<0?NULL:g_strdup(o->modes[k]);g_ptr_array_add(choices,c);elm_hoversel_item_add(o->picker,k<0?"Off":o->modes[k],NULL,ELM_ICON_NONE,choose,c);}
 o->xs=o->ys=NULL;if(fine){Evas_Object *coords=box(edit,1);pack(edit,coords);
 label(coords,"Across");o->xs=elm_spinner_add(coords);elm_spinner_min_max_set(o->xs,0,16384);elm_spinner_step_set(o->xs,10);elm_spinner_value_set(o->xs,o->x);elm_spinner_label_format_set(o->xs,"%.0f");evas_object_size_hint_min_set(o->xs,105,32);pack(coords,o->xs);label(coords,"Down");o->ys=elm_spinner_add(coords);elm_spinner_min_max_set(o->ys,0,16384);elm_spinner_step_set(o->ys,10);elm_spinner_value_set(o->ys,o->y);elm_spinner_label_format_set(o->ys,"%.0f");evas_object_size_hint_min_set(o->ys,105,32);pack(coords,o->ys);evas_object_smart_callback_add(o->xs,"changed",position,o);evas_object_smart_callback_add(o->ys,"changed",position,o);}
 }
 if(fine){label(edit,"Positions are measured from the top-left of your desktop, in pixels.");}elm_object_disabled_set(edit,!supported||!outputs->len);
 label(body,"This first pass changes the current session. E may reapply its saved layout at login.");elm_object_content_set(scroll,body);evas_object_show(body);
}
static void read_state(void){if(worker||!helper)return;char *q=g_shell_quote(helper),*cmd=g_strdup_printf("python3 %s snapshot",q);g_free(q);reply=g_string_new(NULL);trial=0;worker=ecore_exe_pipe_run(cmd,ECORE_EXE_PIPE_READ|ECORE_EXE_TERM_WITH_PARENT,NULL);g_free(cmd);if(!worker){g_string_free(reply,TRUE);reply=NULL;status("Could not read displays.");}}
static void record(const char *line){char **f=g_strsplit(line,"\t",-1);unsigned count=g_strv_length(f);for(unsigned n=0;n<count;n++){char *s=g_uri_unescape_string(f[n],NULL);if(s){g_free(f[n]);f[n]=s;}}
 if(count>=2){if(!strcmp(f[0],"output")&&count==7){Output *o=g_new0(Output,1);o->name=g_strdup(f[1]);o->mode=strcmp(f[2],"off")?g_strdup(f[2]):NULL;o->x=atoi(f[3]);o->y=atoi(f[4]);o->primary=atoi(f[5]);o->modes=g_strsplit(f[6],",",-1);g_ptr_array_add(outputs,o);}else if(!strcmp(f[0],"supported"))supported=atoi(f[1]);else {if(strcmp(f[0],"ready")||!result)status(f[1]);if(!strcmp(f[0],"kept")||!strcmp(f[0],"reverted")||!strcmp(f[0],"error")){g_free(result);result=g_strdup(f[1]);}if(!strcmp(f[0],"pending")){pending=1;remaining=15;pack(decision_row,keep);pack(decision_row,revert);elm_scroller_region_show(scroll,0,0,650,120);elm_object_text_set(notice,"Can you see everything? Keep these settings or wait to revert.");elm_object_disabled_set(keep,EINA_FALSE);elm_object_disabled_set(revert,EINA_FALSE);timer=ecore_timer_add(1,tick,NULL);}}}g_strfreev(f);
}
static Eina_Bool data_event(void *data,int type,void *event){(void)data;(void)type;Ecore_Exe_Event_Data *e=event;if(e->exe==worker){if(trial&&e->lines){for(int n=0;e->lines[n].line;n++)record(e->lines[n].line);}else if(reply&&reply->len+(size_t)e->size<1024*1024)g_string_append_len(reply,e->data,e->size);}return ECORE_CALLBACK_PASS_ON;}
static Eina_Bool exit_event(void *data,int type,void *event){(void)data;(void)type;Ecore_Exe_Event_Del *e=event;if(e->exe!=worker)return ECORE_CALLBACK_PASS_ON;worker=NULL;if(timer){ecore_timer_del(timer);timer=NULL;}pending=0;if(!trial){g_ptr_array_set_size(outputs,0);supported=0;char **lines=g_strsplit(reply->str,"\n",-1);for(int n=0;lines[n];n++)record(lines[n]);g_strfreev(lines);}g_string_free(reply,TRUE);reply=NULL;if(e->exit_code&&!result)status("Display operation failed. Check the display connection and refresh.");if(trial){trial=0;read_state();}else render();return ECORE_CALLBACK_PASS_ON;}
static void deleted(void *data,Evas *e,Evas_Object *o,void *event){(void)data;(void)e;(void)o;(void)event;scroll=body=edit=keep=revert=notice=NULL;}
void displays_init(Evas_Object *parent,void (*cb)(const char *)){host=parent;report=cb;helper=g_strdup(getenv("WORKSTATION_DISPLAY_HELPER"));outputs=g_ptr_array_new_with_free_func(output_free);choices=g_ptr_array_new_with_free_func(choice_free);drags=g_ptr_array_new_with_free_func(g_free);if(frost_preview()){widget_theme=elm_theme_new();elm_theme_set(widget_theme,"default");elm_theme_extension_add(widget_theme,getenv("WORKSTATION_THEME"));}scroll=elm_scroller_add(parent);elm_object_theme_set(scroll,widget_theme);if(frost_preview())edje_object_color_class_set(elm_layout_edje_get(scroll),"/bg/normal/scroller/base",0,0,0,0,255,255,255,255,255,255,255,255);if(frost_preview())edje_object_color_class_set(elm_layout_edje_get(scroll),"/shadow/normal/scroller",0,0,0,0,255,255,255,255,255,255,255,255);elm_scroller_policy_set(scroll,ELM_SCROLLER_POLICY_OFF,ELM_SCROLLER_POLICY_AUTO);evas_object_event_callback_add(scroll,EVAS_CALLBACK_DEL,deleted,NULL);elm_object_part_content_set(parent,"display.content",scroll);evas_object_show(scroll);data_handler=ecore_event_handler_add(ECORE_EXE_EVENT_DATA,data_event,NULL);exit_handler=ecore_event_handler_add(ECORE_EXE_EVENT_DEL,exit_event,NULL);status("Reading displays…");render();}
void displays_visible(Eina_Bool visible){int was=active;active=visible;if(visible){if(!was&&!pending)read_state();if(report)report(displays_status());}}
char *displays_diagnostics(void){GString *s=g_string_new("Display draft (Refresh reads current state)\n");for(unsigned n=0;n<outputs->len;n++){Output *o=g_ptr_array_index(outputs,n);g_string_append_printf(s,"%s: %s at %d,%d%s\n",o->name,o->mode?o->mode:"off",o->x,o->y,o->primary?" main":"");}return g_string_free(s,FALSE);}
void displays_shutdown(void){if(timer)ecore_timer_del(timer);ecore_event_handler_del(data_handler);ecore_event_handler_del(exit_handler);if(worker){if(trial){ecore_exe_send(worker,"revert\n",7);ecore_exe_close_stdin(worker);}else ecore_exe_terminate(worker);}if(scroll)evas_object_del(scroll);if(reply)g_string_free(reply,TRUE);g_ptr_array_free(choices,TRUE);g_ptr_array_free(drags,TRUE);g_ptr_array_free(outputs,TRUE);g_free(helper);g_free(message);g_free(result);if(widget_theme)elm_theme_free(widget_theme);}
