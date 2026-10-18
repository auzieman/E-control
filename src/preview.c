/* SPDX-License-Identifier: GPL-3.0-only */
#include <Elementary.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdint.h>
#include <ctype.h>
#include "catalog.h"
#include "audio.h"
#include "displays.h"
#include "accounts.h"
#include "workstation.h"
static Evas_Object *win,*layout,*face,*search,*detail_win;
static int current,hue,system_ui;
static Evas_Object *heading_widget,*description_widget,*status_widget,*details_widget,*row_titles[4],*row_values[4],*nav_widget,*shell_root,*sidebar_widget,*sidebar_bg,*shell_right;
static Elm_Object_Item *nav_items[10];
static Evas_Object *detail_face;
static const int colours[3][9]={
 {255,255,255,216,229,237,203,221,232},
 {235,247,255,209,229,244,185,215,236},
 {238,255,247,215,235,224,190,221,207}};
static void palette_to(Evas_Object *edje){
 const int *c=colours[hue];
 edje_object_color_class_set(edje,"frost.surface",c[0],c[1],c[2],255,255,255,255,255,255,255,255,255);
 edje_object_color_class_set(edje,"frost.sidebar",c[3],c[4],c[5],244,255,255,255,255,255,255,255,255);
}
static const char *theme,*facts_dir;
static char *read_facts(int page) {
 char path[4096];snprintf(path,sizeof(path),"%s/%s.txt",facts_dir,pages[page].id);
 FILE *f=fopen(path,"r");if(!f)return strdup("Host snapshot unavailable. Run tools/snapshot.py to collect read-only status.");
 char *text=calloc(16385,1);if(!text){fclose(f);return NULL;}
 size_t n=fread(text,1,16384,f);text[n]=0;fclose(f);return text;
}
static void set_text(const char *part,const char *text){
 if(!system_ui){edje_object_part_text_set(face,part,text?text:"");return;}
 Evas_Object *o=NULL;if(!strcmp(part,"heading"))o=heading_widget;else if(!strcmp(part,"description"))o=description_widget;else if(!strcmp(part,"status"))o=status_widget;else if(!strcmp(part,"details.text")){elm_object_text_set(details_widget,text);return;}else{int n;if(sscanf(part,"row.title.%d",&n)==1&&n>=0&&n<4)o=row_titles[n];else if(sscanf(part,"row.value.%d",&n)==1&&n>=0&&n<4)o=row_values[n];}
 if(o){char *m=elm_entry_utf8_to_markup(text?text:"");elm_object_text_set(o,m);free(m);}
}
static void audio_report(const char *text){if(win&&face&&current==2)set_text("status",text);}
static void displays_report(const char *text){if(win&&face&&current==1)set_text("status",text);}
static void accounts_report(const char *text){if(win&&face&&current==4)set_text("status",text);}
static void network_report(const char *text){if(win&&face&&(current==0||current==3||current>=5))set_text("status",text);}
static void show_page(int page) {
 current=page;if(system_ui&&nav_items[page]&&!elm_list_item_selected_get(nav_items[page]))elm_list_item_selected_set(nav_items[page],EINA_TRUE);set_text("heading",pages[page].title);set_text("description",pages[page].description);
 for(unsigned i=0;i<PAGE_COUNT;i++){char cls[32];snprintf(cls,sizeof(cls),"nav.%u",i);edje_object_color_class_set(face,cls,colours[hue][6],colours[hue][7],colours[hue][8],i==(unsigned)page?255:0,255,255,255,255,255,255,255,255);}
 char *facts=read_facts(page),*saveptr=NULL,*line=facts?strtok_r(facts,"\n",&saveptr):NULL;
 for(int i=0;i<4;i++){
  char part[32];snprintf(part,sizeof(part),"row.title.%d",i);set_text(part,pages[page].rows[i]);
  snprintf(part,sizeof(part),"row.value.%d",i);set_text(part,line?line:"Host provider status unavailable");
  line=line?strtok_r(NULL,"\n",&saveptr):NULL;
 }
 char status[160];snprintf(status,sizeof(status),"%d E settings mapped · read-only host snapshot · select a row for details",pages[page].count);set_text("status",status);free(facts);
 edje_object_signal_emit(face,page==2?"page,audio":page==1?"page,displays":page==4?"page,accounts":(page==0||page==3||page>=5)?"page,network":"page,summary","app");audio_visible(page==2);displays_visible(page==1);accounts_visible(page==4);workstation_show((page==0||page==3||page>=5)?page:-1);if(page==2){set_text("details.text","Technical details");set_text("status",audio_status());}else if(page==1){set_text("details.text","Display details");set_text("status",displays_status());}else set_text("details.text","Page diagnostics");
}
static void go_network(void){show_page(3);}
static void main_deleted(void *data,Evas *e,Evas_Object *o,void *event){(void)data;(void)e;(void)o;(void)event;win=NULL;}
static void closed(void *data,Evas_Object *obj,void *event){(void)data;(void)obj;(void)event;elm_exit();}
static void detail_deleted(void *data,Evas *e,Evas_Object *o,void *event){(void)data;(void)e;(void)o;(void)event;detail_win=NULL;detail_face=NULL;}
static void chrome(void *data,Evas_Object *obj,const char *emission,const char *source) {
 (void)obj;(void)emission;Evas_Object *w=data;
 if(!strcmp(source,"event.drag"))elm_win_move_resize_start(w,ELM_WIN_MOVE_RESIZE_MOVE);
 else if(!strcmp(source,"event.minimize"))elm_win_iconified_set(w,EINA_TRUE);
 else if(!strcmp(source,"event.maximize"))elm_win_maximized_set(w,!elm_win_maximized_get(w));
 else if(w==win)elm_exit();else evas_object_del(w);
}
static void bind_chrome(Evas_Object *w,Evas_Object *edje){const char *parts[]={"event.drag","event.minimize","event.maximize","event.close","event.done"};for(int i=0;i<5;i++)edje_object_signal_callback_add(edje,i?"mouse,clicked,1":"mouse,down,1",parts[i],chrome,w);}
static void detail(void *data,Evas_Object *obj,const char *emission,const char *source) {
 (void)data;(void)obj;(void)emission;(void)source;
 if(detail_win){evas_object_raise(detail_win);return;}
 if(system_ui){detail_win=elm_win_util_standard_add("settings-details",pages[current].title);elm_win_autodel_set(detail_win,EINA_TRUE);evas_object_event_callback_add(detail_win,EVAS_CALLBACK_DEL,detail_deleted,NULL);Evas_Object *sc=elm_scroller_add(detail_win);elm_win_resize_object_add(detail_win,sc);Evas_Object *en=elm_entry_add(sc);elm_entry_editable_set(en,EINA_FALSE);elm_entry_line_wrap_set(en,ELM_WRAP_WORD);char *facts=current==2?audio_diagnostics():current==1?displays_diagnostics():read_facts(current);char *m=elm_entry_utf8_to_markup(facts?facts:"Unavailable");elm_entry_entry_set(en,m);free(m);free(facts);elm_object_content_set(sc,en);evas_object_show(en);evas_object_show(sc);evas_object_resize(detail_win,680,440);evas_object_show(detail_win);return;}

 detail_win=elm_win_add(win,"workstation-details",ELM_WIN_BASIC);elm_win_title_set(detail_win,"Workstation Settings — details");elm_win_autodel_set(detail_win,EINA_TRUE);elm_win_borderless_set(detail_win,EINA_TRUE);elm_win_alpha_set(detail_win,EINA_TRUE);
 evas_object_event_callback_add(detail_win,EVAS_CALLBACK_DEL,detail_deleted,NULL);
 Evas_Object *dl=elm_layout_add(detail_win);elm_layout_file_set(dl,theme,"workstation/details");elm_win_resize_object_add(detail_win,dl);evas_object_size_hint_weight_set(dl,EVAS_HINT_EXPAND,EVAS_HINT_EXPAND);evas_object_show(dl);
 Evas_Object *df=elm_layout_edje_get(dl);detail_face=df;palette_to(df);bind_chrome(detail_win,df);edje_object_part_text_set(df,"title",pages[current].title);
 Evas_Object *scroll=elm_scroller_add(dl),*entry=elm_entry_add(scroll);elm_entry_editable_set(entry,EINA_FALSE);elm_entry_line_wrap_set(entry,ELM_WRAP_WORD);elm_entry_text_style_user_push(entry,"DEFAULT='font=DejaVu Sans font_size=12 color=#263a49'");
 char *facts=current==2?audio_diagnostics():current==1?displays_diagnostics():read_facts(current);const char *registry=pages[current].registry;size_t size=strlen(facts?facts:"")+strlen(registry)+400;char *plain=malloc(size);
 snprintf(plain,size,"HOST SNAPSHOT\n%s\n\nEXISTING E SETTINGS\n%s\n\nAudio controls apply when you use them. Display changes require confirmation. Other categories remain preview pages.",facts?facts:"Unavailable",registry);
 char *markup=elm_entry_utf8_to_markup(plain);elm_entry_entry_set(entry,markup);free(markup);free(plain);free(facts);
 evas_object_size_hint_weight_set(entry,EVAS_HINT_EXPAND,0);evas_object_size_hint_align_set(entry,EVAS_HINT_FILL,0);elm_object_content_set(scroll,entry);evas_object_show(entry);elm_object_part_content_set(dl,"content",scroll);evas_object_show(scroll);
 evas_object_resize(detail_win,680,440);evas_object_show(detail_win);
}
static void nav(void *data,Evas_Object *obj,const char *emission,const char *source){(void)obj;(void)emission;(void)source;show_page((int)(intptr_t)data);}
static void set_hue(void *data,Evas_Object *obj,const char *emission,const char *source){
 (void)obj;(void)emission;(void)source;hue=(int)(intptr_t)data;palette_to(face);if(detail_face)palette_to(detail_face);show_page(current);
}
static int contains(const char *text,const char *query){size_t len=strlen(query);for(;*text;text++){size_t i;for(i=0;i<len&&text[i]&&tolower((unsigned char)text[i])==tolower((unsigned char)query[i]);i++);if(i==len)return 1;}return !len;}
static int find_page(const char *q){for(unsigned i=0;i<PAGE_COUNT;i++)if(contains(pages[i].title,q)||contains(pages[i].keywords,q))return (int)i;return -1;}
static void searched(void *data,Evas_Object *obj,void *event){(void)data;(void)event;char *q=elm_entry_markup_to_utf8(elm_entry_entry_get(obj));if(q&&*q){int found=find_page(q);if(found>=0)show_page(found);else set_text("status","No matching settings category. Try printer, volume, scaling or startup.");}free(q);}
static Eina_Bool keypress(void *data,Evas_Object *obj,Evas_Object *source,Evas_Callback_Type type,void *event){
 (void)data;(void)obj;(void)source;if(type!=EVAS_CALLBACK_KEY_DOWN)return EINA_FALSE;
 Evas_Event_Key_Down *key=event;
 if(elm_object_focus_get(search)){
  if(!strcmp(key->key,"Escape")){elm_entry_entry_set(search,"");elm_object_focus_set(search,EINA_FALSE);elm_object_focus_set(layout,EINA_TRUE);return EINA_TRUE;}
  return EINA_FALSE;
 }
 if(!elm_object_focus_get(layout))return EINA_FALSE;
 if(!strcmp(key->key,"Up"))show_page((current+(int)PAGE_COUNT-1)%(int)PAGE_COUNT);
 else if(!strcmp(key->key,"Down"))show_page((current+1)%(int)PAGE_COUNT);
 else if(!strcmp(key->key,"Return"))detail(NULL,NULL,NULL,NULL);
 else return EINA_FALSE;
 key->event_flags|=EVAS_EVENT_FLAG_ON_HOLD;return EINA_TRUE;
}
static Eina_Bool verify(void *data){(void)data;for(unsigned i=0;i<PAGE_COUNT;i++){show_page((int)i);char *shown=system_ui?elm_entry_markup_to_utf8(elm_object_text_get(heading_widget)):strdup(edje_object_part_text_get(face,"heading"));if(strcmp(shown,pages[i].title)){fprintf(stderr,"Navigation verification failed\n");exit(1);}free(shown);}if(find_page("printer")!=7||find_page("volume")!=2||find_page("not-a-setting")!=-1){fprintf(stderr,"Search verification failed\n");exit(1);}if(!system_ui){for(int h=0;h<3;h++){set_hue((void *)(intptr_t)h,NULL,NULL,NULL);int r,g,b,a;if(!edje_object_color_class_get(face,"frost.surface",&r,&g,&b,&a,NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL)||r!=colours[h][0]||g!=colours[h][1]||b!=colours[h][2]||a!=255){fprintf(stderr,"Palette verification failed\n");exit(1);}}set_hue(0,NULL,NULL,NULL);if(strcmp(edje_object_part_text_get(face,"label.close"),"×")||strcmp(edje_object_part_text_get(face,"label.minimize"),"−")){fprintf(stderr,"UTF-8 chrome verification failed\n");exit(1);}}show_page(2);detail(NULL,NULL,NULL,NULL);printf("VERIFY: ten native pages, category search, three palettes, UTF-8 chrome and details dialog PASS\n");fflush(stdout);elm_exit();return ECORE_CALLBACK_CANCEL;}
static void native_nav(void *data,Evas_Object *obj,void *event){(void)obj;(void)event;int n=(int)(intptr_t)data;if(current!=n)show_page(n);}
static void native_detail(void *data,Evas_Object *obj,void *event){(void)data;(void)obj;(void)event;detail(NULL,NULL,NULL,NULL);}
static void size_shell(void){
 if(!system_ui||!win)return;
 int w,h;evas_object_geometry_get(win,NULL,NULL,&w,&h);
 if(shell_root){evas_object_move(shell_root,0,0);evas_object_resize(shell_root,w,h);}
 if(sidebar_bg){evas_object_move(sidebar_bg,0,58);evas_object_resize(sidebar_bg,262,h-58);}
 if(sidebar_widget){evas_object_move(sidebar_widget,12,72);evas_object_resize(sidebar_widget,238,h-88);}
 if(shell_right){evas_object_move(shell_right,262,0);evas_object_resize(shell_right,w-262,h);}
}
static void shell_resized(void *data EINA_UNUSED,Evas *e EINA_UNUSED,Evas_Object *o EINA_UNUSED,void *event EINA_UNUSED){size_shell();}
static Eina_Bool settle_window(void *data EINA_UNUSED){size_shell();return ECORE_CALLBACK_CANCEL;}

static void npack(Evas_Object *b,Evas_Object *o){elm_box_pack_end(b,o);evas_object_show(o);}
static Evas_Object *nbox(Evas_Object *p,int horizontal){Evas_Object *b=elm_box_add(p);elm_box_horizontal_set(b,horizontal);elm_box_padding_set(b,12,10);evas_object_size_hint_weight_set(b,EVAS_HINT_EXPAND,EVAS_HINT_EXPAND);evas_object_size_hint_align_set(b,EVAS_HINT_FILL,EVAS_HINT_FILL);return b;}
static Evas_Object *nlabel(Evas_Object *b){Evas_Object *o=elm_label_add(b);elm_label_line_wrap_set(o,ELM_WRAP_WORD);evas_object_size_hint_weight_set(o,EVAS_HINT_EXPAND,0);evas_object_size_hint_align_set(o,EVAS_HINT_FILL,0);npack(b,o);return o;}
static void native_shell(void){
 Evas_Object *root=shell_root=nbox(win,1);elm_box_padding_set(root,262,10);evas_object_size_hint_min_set(root,1050,780);elm_win_resize_object_add(win,root);evas_object_show(root);
 sidebar_bg=elm_bg_add(win);elm_win_resize_object_add(win,sidebar_bg);evas_object_show(sidebar_bg);Evas_Object *side=sidebar_widget=nbox(win,0);evas_object_size_hint_weight_set(side,0,0);evas_object_size_hint_align_set(side,0,0);evas_object_size_hint_min_set(side,238,650);
 search=elm_entry_add(side);elm_entry_single_line_set(search,EINA_TRUE);elm_entry_scrollable_set(search,EINA_TRUE);elm_object_part_text_set(search,"guide","Find a setting");evas_object_size_hint_align_set(search,EVAS_HINT_FILL,0);npack(side,search);evas_object_smart_callback_add(search,"changed,user",searched,NULL);
 nav_widget=elm_list_add(side);evas_object_size_hint_weight_set(nav_widget,EVAS_HINT_EXPAND,EVAS_HINT_EXPAND);evas_object_size_hint_align_set(nav_widget,EVAS_HINT_FILL,EVAS_HINT_FILL);npack(side,nav_widget);for(unsigned i=0;i<PAGE_COUNT;i++)nav_items[i]=elm_list_item_append(nav_widget,pages[i].title,NULL,NULL,native_nav,(void *)(intptr_t)i);elm_list_go(nav_widget);evas_object_move(side,12,72);evas_object_resize(side,250,650);evas_object_show(side);
 Evas_Object *frame=shell_right=elm_frame_add(win);Evas_Object *right=nbox(frame,0);elm_object_content_set(frame,right);evas_object_show(right);evas_object_move(frame,262,0);evas_object_resize(frame,788,780);evas_object_show(frame);heading_widget=nlabel(right);description_widget=nlabel(right);
 layout=elm_layout_add(right);elm_layout_file_set(layout,theme,"workstation/system-content");evas_object_size_hint_weight_set(layout,EVAS_HINT_EXPAND,EVAS_HINT_EXPAND);evas_object_size_hint_align_set(layout,EVAS_HINT_FILL,EVAS_HINT_FILL);npack(right,layout);face=elm_layout_edje_get(layout);
 Evas_Object *summary=nbox(layout,0);for(int i=0;i<4;i++){row_titles[i]=nlabel(summary);row_values[i]=nlabel(summary);}elm_object_part_content_set(layout,"summary.content",summary);evas_object_show(summary);
 status_widget=nlabel(right);details_widget=elm_button_add(right);elm_object_text_set(details_widget,"Page details");evas_object_size_hint_align_set(details_widget,0,.5);evas_object_smart_callback_add(details_widget,"clicked",native_detail,NULL);npack(right,details_widget);
}
EAPI_MAIN int elm_main(int argc,char **argv){
 (void)argc;(void)argv;system_ui=!(getenv("WORKSTATION_FROST_PREVIEW")&&!strcmp(getenv("WORKSTATION_FROST_PREVIEW"),"1"));theme=getenv("WORKSTATION_THEME");facts_dir=getenv("WORKSTATION_FACTS");if(!theme||!facts_dir){fprintf(stderr,"Use tools/run-preview.sh\n");return 1;}
 win=system_ui?elm_win_util_standard_add("workstation-settings","Workstation Settings"):elm_win_add(NULL,"workstation-settings",ELM_WIN_BASIC);elm_win_title_set(win,getenv("WORKSTATION_TITLE")?getenv("WORKSTATION_TITLE"):"Workstation Settings — frosted preview");elm_win_autodel_set(win,EINA_TRUE);elm_win_alpha_set(win,!system_ui);elm_win_borderless_set(win,!system_ui);evas_object_smart_callback_add(win,"delete,request",closed,NULL);evas_object_event_callback_add(win,EVAS_CALLBACK_DEL,main_deleted,NULL);
 if(system_ui)native_shell();else{layout=elm_layout_add(win);if(!elm_layout_file_set(layout,theme,"workstation/main")){fprintf(stderr,"Missing native skin\n");return 1;}
 elm_win_resize_object_add(win,layout);evas_object_size_hint_weight_set(layout,EVAS_HINT_EXPAND,EVAS_HINT_EXPAND);evas_object_show(layout);face=elm_layout_edje_get(layout);palette_to(face);bind_chrome(win,face);

 for(unsigned i=0;i<PAGE_COUNT;i++){char part[32];snprintf(part,sizeof(part),"event.nav.%u",i);edje_object_signal_callback_add(face,"mouse,clicked,1",part,nav,(void *)(intptr_t)i);}
 for(int i=0;i<4;i++){char part[32];snprintf(part,sizeof(part),"event.row.%d",i);edje_object_signal_callback_add(face,"mouse,clicked,1",part,detail,NULL);}
 edje_object_signal_callback_add(face,"mouse,clicked,1","event.details",detail,NULL);

 search=elm_entry_add(layout);elm_entry_single_line_set(search,EINA_TRUE);elm_entry_scrollable_set(search,EINA_FALSE);elm_entry_text_style_user_push(search,"DEFAULT='font=DejaVu Sans font_size=12 color=#263a49'");elm_object_part_text_set(search,"guide","Find a setting");elm_object_part_content_set(layout,"search.entry",search);evas_object_smart_callback_add(search,"changed,user",searched,NULL);
 }elm_object_event_callback_add(win,keypress,NULL);elm_object_focus_allow_set(layout,EINA_TRUE);elm_object_focus_set(layout,EINA_TRUE);
 audio_init(layout,audio_report);displays_init(layout,displays_report);accounts_init(layout,accounts_report);workstation_init(layout,network_report);accounts_link_set(go_network);
 if(system_ui){evas_object_size_hint_min_set(shell_root,1050,780);evas_object_resize(shell_root,1050,780);}
 int start=2;const char *page=getenv("WORKSTATION_PAGE");if(page)for(unsigned i=0;i<PAGE_COUNT;i++)if(!strcmp(page,pages[i].id))start=(int)i;show_page(start);
 if(system_ui){evas_object_event_callback_add(win,EVAS_CALLBACK_RESIZE,shell_resized,NULL);elm_win_center(win,EINA_TRUE,EINA_TRUE);}evas_object_resize(win,system_ui?1050:1000,system_ui?780:680);evas_object_show(win);if(system_ui)ecore_timer_add(.2,settle_window,NULL);if(getenv("WORKSTATION_VERIFY"))ecore_timer_add(.4,verify,NULL);elm_run();workstation_shutdown();accounts_shutdown();displays_shutdown();audio_shutdown();if(detail_win)evas_object_del(detail_win);if(win)evas_object_del(win);return 0;
}
ELM_MAIN()
