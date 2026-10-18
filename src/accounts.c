/* SPDX-License-Identifier: GPL-3.0-only */
#include "accounts.h"
#include <glib.h>
#include <unistd.h>
#include <stdlib.h>
#include <stdio.h>
#include <string.h>
static int frost_preview(void){const char *s=getenv("WORKSTATION_FROST_PREVIEW");return s&&!strcmp(s,"1");}
typedef struct {char *name,*full,*home,*groups,*primary,*fingerprint;int uid;} User;
typedef struct {char *name;Evas_Object *check;} GroupCheck;
static Evas_Object *parent,*scrolls[2],*bodies[2],*name_entry,*full_entry,*pw_entry,*confirm_entry,*admin_check,*save_button,*hint,*services_entry,*ports_entry,*vpn_name,*vpn_file;
static Elm_Theme *theme;
static GPtrArray *users,*groups,*checks,*vpns,*ifaces,*wifis,*bts;
static Ecore_Exe *worker;
static Ecore_Event_Handler *data_handler,*exit_handler;
static Ecore_Timer *lock_timer;
static GString *reply;
static char *provider,*message,*selected,*form,*zone_services,*zone_ports,*zone_hash,*profile_text;
static int active_page=-1,account_tab,network_tab,unlocked,wheel_policy,helper_ready;
static void (*reports[2])(const char *),(*open_network)(void);
static void render(int page);
static void send_request(GString *request);
static void status(const char *text){g_free(message);message=g_strdup(text);if(active_page>=0&&reports[active_page])reports[active_page](message);}
static void wipe(void *ptr,size_t size){volatile unsigned char *p=ptr;while(size--)*p++=0;}
static void user_free(void *ptr){User *u=ptr;g_free(u->name);g_free(u->full);g_free(u->home);g_free(u->groups);g_free(u->primary);g_free(u->fingerprint);g_free(u);}
static void check_free(void *ptr){GroupCheck *c=ptr;g_free(c->name);g_free(c);}
static void pack(Evas_Object *b,Evas_Object *o){elm_box_pack_end(b,o);evas_object_show(o);}
static Evas_Object *box(Evas_Object *p,int horizontal){Evas_Object *b=elm_box_add(p);elm_box_horizontal_set(b,horizontal);elm_box_padding_set(b,10,10);elm_box_align_set(b,0,0);evas_object_size_hint_weight_set(b,EVAS_HINT_EXPAND,0);evas_object_size_hint_align_set(b,EVAS_HINT_FILL,0);return b;}
static Evas_Object *label(Evas_Object *b,const char *s,int size){Evas_Object *o=elm_label_add(b);char *m=frost_preview()?g_markup_printf_escaped("<align=left><color=#263a49><font_size=%d>%s</font_size></color></align>",size,s):g_markup_printf_escaped(size>=16?"<align=left><b>%s</b></align>":"<align=left>%s</align>",s);elm_object_text_set(o,m);g_free(m);elm_label_line_wrap_set(o,ELM_WRAP_WORD);elm_label_wrap_width_set(o,650);evas_object_size_hint_weight_set(o,EVAS_HINT_EXPAND,0);evas_object_size_hint_align_set(o,EVAS_HINT_FILL,.5);pack(b,o);return o;}
static Evas_Object *button(Evas_Object *b,const char *s,Evas_Smart_Cb cb,void *data,int enabled){Evas_Object *o=elm_button_add(b);if(frost_preview())elm_object_style_set(o,"frost-action");elm_object_text_set(o,s);elm_object_disabled_set(o,!enabled||worker);if(cb)evas_object_smart_callback_add(o,"clicked",cb,data);pack(b,o);return o;}
static Evas_Object *entry(Evas_Object *b,const char *caption,const char *value,int secret){label(b,caption,12);Evas_Object *o=elm_entry_add(b);elm_entry_single_line_set(o,EINA_TRUE);elm_entry_scrollable_set(o,EINA_TRUE);elm_entry_password_set(o,secret);elm_entry_prediction_allow_set(o,EINA_FALSE);if(frost_preview())elm_entry_text_style_user_push(o,"DEFAULT='font=DejaVu Sans font_size=13 color=#263a49'");char *markup=elm_entry_utf8_to_markup(value?value:"");elm_entry_entry_set(o,markup);free(markup);evas_object_size_hint_weight_set(o,EVAS_HINT_EXPAND,0);evas_object_size_hint_align_set(o,EVAS_HINT_FILL,.5);evas_object_size_hint_min_set(o,360,32);elm_object_disabled_set(o,!unlocked||worker);pack(b,o);return o;}
static Evas_Object *check(Evas_Object *b,const char *text,int state,int enabled){Evas_Object *row=box(b,1);pack(b,row);Evas_Object *o=elm_check_add(row);elm_check_state_set(o,state);elm_object_disabled_set(o,!enabled);pack(row,o);label(row,text,13);return o;}
static char *plain(Evas_Object *o){return o?elm_entry_markup_to_utf8(elm_entry_entry_get(o)):strdup("");}
static void secret_free(char *s){if(s){wipe(s,strlen(s));free(s);}}
static void clear_secret(void){if(pw_entry)elm_entry_entry_set(pw_entry,"");if(confirm_entry)elm_entry_entry_set(confirm_entry,"");if(profile_text){wipe(profile_text,strlen(profile_text));g_clear_pointer(&profile_text,g_free);}}
static User *chosen(void){for(unsigned i=0;i<users->len;i++){User *u=g_ptr_array_index(users,i);if((account_tab==0&&u->uid==(int)getuid())||(account_tab==1&&selected&&!strcmp(selected,u->name)))return u;}return NULL;}
static int member(const char *csv,const char *name){char **parts=g_strsplit(csv?csv:"",",",-1);int found=0;for(int i=0;parts[i];i++)if(!strcmp(parts[i],name))found=1;g_strfreev(parts);return found;}
/* JSON quoting keeps UTF-8 intact; request text never goes through a shell. */
static void quoted(GString *s,const char *text){g_string_append_c(s,'"');for(const unsigned char *p=(const unsigned char *)text;*p;p++){if(*p=='"'||*p=='\\'){g_string_append_c(s,'\\');g_string_append_c(s,*p);}else if(*p<32)g_string_append_printf(s,"\\u%04x",*p);else g_string_append_c(s,*p);}g_string_append_c(s,'"');}
static void pair(GString *s,const char *key,const char *value){g_string_append_c(s,',');quoted(s,key);g_string_append_c(s,':');quoted(s,value);}
static GString *request(const char *op){GString *s=g_string_new("{\"op\":");quoted(s,op);return s;}
static void simple(const char *op){GString *s=request(op);g_string_append_c(s,'}');send_request(s);}
static void refresh(void *d,Evas_Object *o,void *e){(void)d;(void)o;(void)e;clear_secret();g_clear_pointer(&form,g_free);simple("snapshot");}
static Eina_Bool expire(void *d){(void)d;lock_timer=NULL;unlocked=0;clear_secret();g_clear_pointer(&form,g_free);render(0);render(1);status("Controls locked. Unlock again to edit; the host still checks each save.");return ECORE_CALLBACK_CANCEL;}
static void unlock(void *d,Evas_Object *o,void *e){(void)d;(void)o;(void)e;if(unlocked){if(lock_timer){ecore_timer_del(lock_timer);lock_timer=NULL;}expire(NULL);}else simple("unlock");}
static void change_tab(void *d,Evas_Object *o,void *e){(void)o;(void)e;int v=GPOINTER_TO_INT(d);clear_secret();g_clear_pointer(&form,g_free);if(v<10)account_tab=v;else network_tab=v-10;render(v<10?0:1);}
static void cancel(void *d,Evas_Object *o,void *e){(void)d;(void)o;(void)e;clear_secret();g_clear_pointer(&form,g_free);render(active_page>=0?active_page:0);status("Changes cancelled.");}
static void edit(void *d,Evas_Object *o,void *e){(void)o;(void)e;if(!unlocked)return;clear_secret();g_free(form);form=g_strdup(d);render(active_page);elm_scroller_region_show(scrolls[active_page],0,0,650,120);}
static void select_user(void *d,Evas_Object *o,void *e){(void)o;(void)e;clear_secret();g_clear_pointer(&form,g_free);g_free(selected);selected=g_strdup(d);render(0);}
static void password_hint(void *d,Evas_Object *o,void *e){(void)d;(void)o;(void)e;char *a=plain(pw_entry),*b=plain(confirm_entry);glong length=g_utf8_strlen(a,-1);int valid=length>=8&&length<=1024&&!strcmp(a,b)&&!strchr(a,'\n')&&!strchr(a,'\r');const char *text=length<8?"Use at least 8 characters; a longer passphrase is better.":strcmp(a,b)?"The two passwords do not match.":length>=16?"Passwords match · long passphrase length.":"Passwords match · consider a longer passphrase.";elm_object_text_set(hint,text);elm_object_disabled_set(save_button,!valid||!unlocked||worker);secret_free(a);secret_free(b);}
static void submit(void *d,Evas_Object *o,void *e){(void)d;(void)o;(void)e;if(!form||!unlocked||worker)return;GString *s=request(form);User *u=chosen();
 if(!strcmp(form,"profile")||!strcmp(form,"groups")||!strcmp(form,"password")){if(!u){g_string_free(s,TRUE);return;}pair(s,"name",u->name);pair(s,"expected",u->fingerprint);}
 if(!strcmp(form,"profile")||!strcmp(form,"create")){char *v=plain(full_entry);pair(s,"fullname",v);free(v);}
 if(!strcmp(form,"groups")){g_string_append(s,",\"groups\":[");int count=0;for(unsigned i=0;i<checks->len;i++){GroupCheck *c=g_ptr_array_index(checks,i);if(elm_check_state_get(c->check)){if(count++)g_string_append_c(s,',');quoted(s,c->name);}}if(elm_check_state_get(admin_check)){if(count)g_string_append_c(s,',');quoted(s,"wheel");}g_string_append_c(s,']');}
 if(!strcmp(form,"password")||!strcmp(form,"create")){char *a=plain(pw_entry),*b=plain(confirm_entry);if(strcmp(a,b)||g_utf8_strlen(a,-1)<8||g_utf8_strlen(a,-1)>1024){secret_free(a);secret_free(b);g_string_free(s,TRUE);status("Use matching passwords of at least eight characters.");return;}pair(s,"password",a);secret_free(a);secret_free(b);if(!strcmp(form,"create")){char *n=plain(name_entry);pair(s,"name",n);free(n);g_string_append_printf(s,",\"admin\":%s",elm_check_state_get(admin_check)?"true":"false");}}
 if(!strcmp(form,"firewall")){char *sv=plain(services_entry),*p=plain(ports_entry);g_string_append(s,",\"services\":[");char **parts=g_strsplit(sv,",",-1);int count=0;for(int i=0;parts[i];i++){char *v=g_strstrip(parts[i]);if(*v){if(count++)g_string_append_c(s,',');quoted(s,v);}}g_strfreev(parts);g_string_append_c(s,']');pair(s,"ports",p);pair(s,"expected",zone_hash?zone_hash:"");free(sv);free(p);}
 if(!strcmp(form,"vpn")){char *n=plain(vpn_name);pair(s,"name",n);free(n);if(!profile_text){g_string_free(s,TRUE);status("Choose an OpenVPN profile first.");return;}pair(s,"profile",profile_text);}
 g_string_append_c(s,'}');send_request(s);clear_secret();
}
static void actions(Evas_Object *b,const char *save,int passwords){Evas_Object *row=box(b,1);pack(b,row);save_button=button(row,save,submit,NULL,1);button(row,"Cancel",cancel,NULL,1);if(passwords){evas_object_smart_callback_add(pw_entry,"changed,user",password_hint,NULL);evas_object_smart_callback_add(confirm_entry,"changed,user",password_hint,NULL);hint=label(b,"Use at least 8 characters. The backend also validates the password.",12);password_hint(NULL,NULL,NULL);}}

static void network_link(void *d,Evas_Object *o,void *e){(void)d;(void)o;(void)e;if(open_network)open_network();}

static void terminal_password(void *d,Evas_Object *o,void *e){(void)d;(void)o;(void)e;ecore_exe_run("/usr/bin/terminology -e /usr/bin/passwd",NULL);status("Complete or cancel the existing password prompt in the terminal.");}
static void account_content(Evas_Object *b){
 Evas_Object *tabs=box(b,1);pack(b,tabs);button(tabs,"Your account",change_tab,GINT_TO_POINTER(0),1);button(tabs,"All users",change_tab,GINT_TO_POINTER(1),1);button(tabs,"Security",change_tab,GINT_TO_POINTER(2),1);
 if(account_tab==2){label(b,"Security",18);button(b,"Open firewall configuration",network_link,NULL,1);label(b,"Firewall settings live under Network. Existing E screen-lock configuration remains in E's Settings panel.",13);return;}
 if(account_tab==1&&(!form||strcmp(form,"create"))){label(b,"Login accounts",18);for(unsigned i=0;i<users->len;i++){User *u=g_ptr_array_index(users,i);button(b,u->name,select_user,u->name,1);}button(b,"Add user…",edit,"create",unlocked);}
 User *u=chosen();if(!u&&(!form||strcmp(form,"create"))){label(b,"Choose an account, or unlock to add a new user.",13);return;}
 if(form&&(!strcmp(form,"profile")||!strcmp(form,"groups")||!strcmp(form,"password")||!strcmp(form,"create"))){
  label(b,!strcmp(form,"create")?"New login account":!strcmp(form,"password")?"Set a new password":!strcmp(form,"groups")?"Groups and administrator access":"Edit account details",18);
  if(!strcmp(form,"create")){name_entry=entry(b,"Username (lowercase)","",0);full_entry=entry(b,"Display name","",0);admin_check=check(b,"Administrator (wheel group)",0,wheel_policy);}
  if(!strcmp(form,"profile")){label(b,u->name,13);full_entry=entry(b,"Display name",u->full,0);label(b,"Username, home and primary group are preserved.",12);actions(b,"Save details",0);}
  if(!strcmp(form,"groups")){int is_admin=member(u->groups,"wheel")||!strcmp(u->primary,"wheel");admin_check=check(b,"Administrator (wheel group)",is_admin,wheel_policy&&strcmp(u->primary,"wheel"));label(b,wheel_policy?"The helper recognized the host's unrestricted sudo wheel grant.":"Wheel policy is unverified; changing administrator membership is unavailable.",12);label(b,"Additional groups",15);for(unsigned i=0;i<groups->len;i++){char *name=g_ptr_array_index(groups,i);if(!strcmp(name,"wheel"))continue;GroupCheck *c=g_new0(GroupCheck,1);c->name=g_strdup(name);int primary=!strcmp(name,u->primary);c->check=check(b,name,primary||member(u->groups,name),!primary);g_ptr_array_add(checks,c);}actions(b,"Save memberships",0);}
  if(!strcmp(form,"password")||!strcmp(form,"create")){pw_entry=entry(b,"New password","",1);confirm_entry=entry(b,"Repeat new password","",1);label(b,"This is an authenticated administrator password operation. Passwords are sent through a private pipe, never saved in the form.",12);actions(b,!strcmp(form,"create")?"Create account":"Save password",1);}
  return;
 }
 label(b,"User details",18);full_entry=entry(b,"Display name",u->full,0);elm_object_disabled_set(full_entry,!unlocked);char *s=g_strdup_printf("Username: %s\nHome: %s\nPrimary group: %s",u->name,u->home,u->primary);label(b,s,13);g_free(s);label(b,"Rules and memberships",15);label(b,u->groups&&*u->groups?u->groups:"No additional groups",12);Evas_Object *row=box(b,1);pack(b,row);button(row,"Edit details",edit,"profile",unlocked);button(row,"Groups / Admin",edit,"groups",unlocked);button(row,"Set password",edit,"password",unlocked);if(account_tab==0)button(b,"Use existing password prompt",terminal_password,NULL,g_file_test("/usr/bin/terminology",G_FILE_TEST_IS_EXECUTABLE));
}
static void render(int page){if(!scrolls[page])return;
 /* Forms only exist on the active page; hidden content must not overwrite widget references. */
 if(active_page>=0&&active_page!=page)return;
 if(bodies[page]){elm_object_content_unset(scrolls[page]);evas_object_del(bodies[page]);}
 name_entry=full_entry=pw_entry=confirm_entry=admin_check=save_button=hint=services_entry=ports_entry=vpn_name=vpn_file=NULL;g_ptr_array_set_size(checks,0);
 Evas_Object *b=bodies[page]=box(scrolls[page],0);evas_object_size_hint_min_set(b,650,0);Evas_Object *row=box(b,1);pack(b,row);button(row,unlocked?"Lock controls":"Unlock…",unlock,NULL,helper_ready);button(row,"Refresh",refresh,NULL,1);label(b,helper_ready?(unlocked?"Editing unlocked · each save is authorized by host policy":"Unlock to edit. Authentication may be reused briefly by the host."):"The authenticated helper is not installed. Editing is unavailable.",12);account_content(b);elm_object_content_set(scrolls[page],b);evas_object_show(b);}
static void send_request(GString *r){if(worker){wipe(r->str,r->len);g_string_free(r,TRUE);return;}char *q=g_shell_quote(provider),*cmd=g_strdup_printf("python3 %s",q);g_free(q);reply=g_string_new(NULL);worker=ecore_exe_pipe_run(cmd,ECORE_EXE_PIPE_READ|ECORE_EXE_PIPE_WRITE|ECORE_EXE_TERM_WITH_PARENT,NULL);g_free(cmd);if(!worker){g_string_free(reply,TRUE);reply=NULL;status("Could not start the settings provider.");}else{ecore_exe_send(worker,r->str,(int)r->len);ecore_exe_close_stdin(worker);if(active_page>=0&&bodies[active_page])elm_object_disabled_set(bodies[active_page],EINA_TRUE);status("Checking authorization and settings…");}wipe(r->str,r->len);g_string_free(r,TRUE);}
static Eina_Bool data_event(void *d,int type,void *event){(void)d;(void)type;Ecore_Exe_Event_Data *e=event;if(e->exe==worker&&reply&&reply->len+(size_t)e->size<2*1024*1024)g_string_append_len(reply,e->data,e->size);return ECORE_CALLBACK_PASS_ON;}
static Eina_Bool exit_event(void *d,int type,void *event){(void)d;(void)type;Ecore_Exe_Event_Del *e=event;if(e->exe!=worker)return ECORE_CALLBACK_PASS_ON;worker=NULL;clear_secret();g_clear_pointer(&form,g_free);g_ptr_array_set_size(users,0);g_ptr_array_set_size(groups,0);g_ptr_array_set_size(vpns,0);g_clear_pointer(&zone_hash,g_free);int result=0;char **lines=g_strsplit(reply->str,"\n",-1);
 for(int n=0;lines[n];n++){char **f=g_strsplit(lines[n],"\t",-1);unsigned count=g_strv_length(f);for(unsigned i=0;i<count;i++){char *v=g_uri_unescape_string(f[i],NULL);if(v){g_free(f[i]);f[i]=v;}}
 if(count==2&&!strcmp(f[0],"helper"))helper_ready=atoi(f[1]);else if(count==8&&!strcmp(f[0],"user")){User *u=g_new0(User,1);u->name=g_strdup(f[1]);u->full=g_strdup(f[2]);u->home=g_strdup(f[3]);u->groups=g_strdup(f[4]);u->uid=atoi(f[5]);u->primary=g_strdup(f[6]);u->fingerprint=g_strdup(f[7]);g_ptr_array_add(users,u);}
 else if(count==2&&!strcmp(f[0],"group"))g_ptr_array_add(groups,g_strdup(f[1]));else if(count==2&&!strcmp(f[0],"vpn"))g_ptr_array_add(vpns,g_strdup(f[1]));else if((count==2||count==5)&&(!strcmp(f[0],"iface")||!strcmp(f[0],"wifi")||!strcmp(f[0],"bt"))){GPtrArray *a=!strcmp(f[0],"iface")?ifaces:!strcmp(f[0],"wifi")?wifis:bts;if(!strcmp(f[0],"bt")&&count==5){char *line=g_strdup_printf("%s · %s%s",f[2],!strcmp(f[4],"yes")?"Connected":"Available",!strcmp(f[3],"yes")?" · Paired":"");g_ptr_array_add(a,line);}else g_ptr_array_add(a,g_strdup(f[1]));}else if(count==4&&!strcmp(f[0],"zone")){g_free(zone_services);g_free(zone_ports);g_free(zone_hash);zone_services=g_strdup(f[1]);zone_ports=g_strdup(f[2]);zone_hash=g_strdup(f[3]);}
 else if(count==2&&!strcmp(f[0],"unlocked")){unlocked=1;wheel_policy=atoi(f[1]);if(lock_timer)ecore_timer_del(lock_timer);lock_timer=ecore_timer_add(240,expire,NULL);}
 else if(count==2&&(!strcmp(f[0],"result")||!strcmp(f[0],"error"))){status(f[1]);result=1;}
 g_strfreev(f);
 }
 g_strfreev(lines);g_string_free(reply,TRUE);reply=NULL;if(!result)status(e->exit_code?"Settings could not be read. Refresh to try again.":"Settings loaded. Saving configuration does not enable services.");if(active_page>=0)render(active_page);return ECORE_CALLBACK_PASS_ON;}
static void deleted(void *d,Evas *e,Evas_Object *o,void *event){(void)e;(void)o;(void)event;int p=GPOINTER_TO_INT(d);scrolls[p]=bodies[p]=NULL;name_entry=full_entry=pw_entry=confirm_entry=admin_check=save_button=hint=services_entry=ports_entry=vpn_name=vpn_file=NULL;}
static void init_page(int page,Evas_Object *p,void (*cb)(const char *)){reports[page]=cb;scrolls[page]=elm_scroller_add(p);elm_object_theme_set(scrolls[page],theme);if(frost_preview())edje_object_color_class_set(elm_layout_edje_get(scrolls[page]),"/bg/normal/scroller/base",0,0,0,0,255,255,255,255,255,255,255,255);elm_scroller_policy_set(scrolls[page],ELM_SCROLLER_POLICY_OFF,ELM_SCROLLER_POLICY_AUTO);evas_object_event_callback_add(scrolls[page],EVAS_CALLBACK_DEL,deleted,GINT_TO_POINTER(page));elm_object_part_content_set(p,page?"network.content":"accounts.content",scrolls[page]);evas_object_show(scrolls[page]);}
void accounts_init(Evas_Object *p,void (*cb)(const char *)){parent=p;if(frost_preview()){theme=elm_theme_new();elm_theme_set(theme,"default");elm_theme_extension_add(theme,getenv("WORKSTATION_THEME"));}provider=g_strdup(getenv("WORKSTATION_SETTINGS_PROVIDER"));users=g_ptr_array_new_with_free_func(user_free);groups=g_ptr_array_new_with_free_func(g_free);checks=g_ptr_array_new_with_free_func(check_free);vpns=g_ptr_array_new_with_free_func(g_free);ifaces=g_ptr_array_new_with_free_func(g_free);wifis=g_ptr_array_new_with_free_func(g_free);bts=g_ptr_array_new_with_free_func(g_free);data_handler=ecore_event_handler_add(ECORE_EXE_EVENT_DATA,data_event,NULL);exit_handler=ecore_event_handler_add(ECORE_EXE_EVENT_DEL,exit_event,NULL);init_page(0,p,cb);}
static void visible(int page,Eina_Bool show){if(show&&active_page!=page){clear_secret();g_clear_pointer(&form,g_free);active_page=page;render(page);if(!worker)simple("snapshot");}else if(!show&&active_page==page){clear_secret();g_clear_pointer(&form,g_free);active_page=-1;}if(show&&message&&reports[page])reports[page](message);}
void accounts_visible(Eina_Bool show){visible(0,show);}
void accounts_link_set(void (*cb)(void)){open_network=cb;}
void accounts_shutdown(void){clear_secret();if(worker)ecore_exe_terminate(worker);if(lock_timer)ecore_timer_del(lock_timer);ecore_event_handler_del(data_handler);ecore_event_handler_del(exit_handler);for(int i=0;i<2;i++)if(scrolls[i])evas_object_del(scrolls[i]);if(reply)g_string_free(reply,TRUE);g_ptr_array_free(users,TRUE);g_ptr_array_free(groups,TRUE);g_ptr_array_free(checks,TRUE);g_ptr_array_free(vpns,TRUE);g_ptr_array_free(ifaces,TRUE);g_ptr_array_free(wifis,TRUE);g_ptr_array_free(bts,TRUE);if(theme)elm_theme_free(theme);g_free(provider);g_free(message);g_free(selected);g_free(form);g_free(zone_services);g_free(zone_ports);g_free(zone_hash);}
