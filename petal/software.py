"""Capability checklist with opt-in, reviewable repository installation."""
import json,os,sys,threading,uuid,time,shutil
from pathlib import Path
from .legacy import Gtk,Gio,GLib,Layer,box,label,button,fit_size
from . import readiness,integrations

class SoftwarePage(Gtk.Box):
 def __init__(self,app,window,values,changed):
  super().__init__(orientation=Gtk.Orientation.VERTICAL,spacing=12);self.app=app;self.window=window;self.values=values;self.changed=changed;self.results=[];self.choices={};self.programs={};self.program_pickers={};self.checking=False;self.generation=0;self.closed=False;self.install_job=None;self.review_window=None;self.cancel_check=threading.Event()
  self.append(label('Choose your conversion programs','title'));self.append(label('See which features work, then choose a program from each list or choose a program elsewhere on your computer. Downloads are optional.','muted',True))
  self.summary=label('Checking your computer…','muted',True);self.append(self.summary);self.rows=box(spacing=10);self.pending_office=None
  actions=box(Gtk.Orientation.HORIZONTAL,8);self.recheck=button('Check again',self.scan);actions.append(self.recheck);self.install_button=button('Review selected downloads…',self.review,'primary');self.install_button.set_sensitive(False);actions.append(self.install_button);self.append(actions)
  self.office_button=button('Choose an external office program…',self.choose_office)
  self.message=label('Checks use temporary sample files. Ready means these checks passed; complex files and unsupported formats can still differ.','muted',True);self.append(self.message)
  self.append(self.rows)
  self.append(label('Installations use your system software manager. It shows sizes and dependencies, asks for confirmation, and may request your password.','muted',True))
  GLib.idle_add(self.scan)
 def dispose_page(self):
  self.closed=True;self.generation+=1;self.cancel_check.set()
  if self.review_window:self.review_window.destroy();self.review_window=None
 def scan(self):
  if self.checking or self.closed:return False
  self.checking=True;self.generation+=1;generation=self.generation;self.recheck.set_sensitive(False);self.install_button.set_sensitive(False);self.office_button.set_sensitive(False);self.summary.set_text('Checking conversion support…');self.rows.set_sensitive(False)
  values=dict(self.values)
  if self.pending_office:values['libreoffice_path']=self.pending_office
  def progress(title):
   def show():
    if not self.closed and generation==self.generation:self.summary.set_text('Checking '+title.lower()+'…')
    return False
   GLib.idle_add(show)
  def worker():
   try:results=readiness.scan(values,progress,self.cancel_check);error=None
   except Exception as e:results=[];error=str(e)
   GLib.idle_add(self.scanned,generation,results,error)
  threading.Thread(target=worker,daemon=True).start();return False
 def scanned(self,generation,results,error):
  if self.closed or generation!=self.generation:return False
  self.checking=False;self.recheck.set_sensitive(True);self.office_button.set_sensitive(True);self.rows.set_sensitive(True)
  if error:self.summary.set_text('Could not finish checking: '+error);return False
  self.results=results;selected={k for k,b in self.choices.items() if b.get_active()};self.choices={};self.program_pickers={}
  if self.pending_office:
   if any(r.key=='office' and r.status=='ready' for r in results):self.save_office(self.pending_office)
   self.pending_office=None
  child=self.rows.get_first_child()
  while child:next_child=child.get_next_sibling();self.rows.remove(child);child=next_child
  for row in results:
   card=box(spacing=5);card.add_css_class('setup-card');top=box(Gtk.Orientation.HORIZONTAL,8);title=label(row.title);title.set_hexpand(True);top.append(title);status=label({'ready':'Ready','partial':'Some features missing','missing':'Not installed','failed':'Needs attention','available':'Available','optional':'Optional'}[row.status]);status.add_css_class('success' if row.status in ('ready','available') else 'muted');top.append(status);card.append(top);card.append(label(row.detail,'muted',True))
   if row.executable and row.key!='builtin':card.append(label('Current program: '+Path(row.executable).name,'muted',True))
   if row.key in readiness.PROGRAMS:
    options=readiness.PROGRAMS[row.key];names=['Choose a program…']+[item[1] for item in options];picker=Gtk.DropDown.new_from_strings(names);picker.set_enable_search(True);picker.set_hexpand(True);current=self.programs.get(row.key);picker.set_selected(next((i+1 for i,item in enumerate(options) if item[0]==current),0));self.program_pickers[row.key]=picker
    choose=box(Gtk.Orientation.HORIZONTAL,8);choose.append(picker);external=button('Other program…',lambda key=row.key:self.choose_program(key));external.set_sensitive(not self.checking);choose.append(external);card.append(choose)
    choice=Gtk.CheckButton(label='Include selected program in downloads');choice.set_sensitive(bool(current));choice.set_active(bool(current) and row.key in selected);choice.connect('toggled',lambda *_:self.update_selection());self.choices[row.key]=choice;card.append(choice)
    link=Gtk.LinkButton.new_with_label(readiness.SOURCES[row.key],'Open selected program’s download page');link.set_visible(bool(current));card.append(link)
    picker.connect('notify::selected',lambda d,*_,key=row.key,c=choice,l=link:self.program_selected(key,d,c,l))
   if row.checks:
    expander=Gtk.Expander(label='What was checked');details=box(spacing=3)
    for name,ok in row.checks.items():details.append(label(('✓ ' if ok else '○ ')+name,'muted',True))
    expander.set_child(details);card.append(expander)
   if row.key=='sharing':card.append(button('Choose a sharing app…',self.choose_sharing))
   self.rows.append(card)
  ready=sum(r.status in ('ready','available') for r in results);self.summary.set_text(f'{ready} of {len(results)} feature groups ready. Choose any extras below.');self.update_selection();return False
 def update_selection(self,*_):self.install_button.set_sensitive(not self.checking and self.install_job is None and any(b.get_active() for b in self.choices.values()))
 def program_selected(self,key,picker,choice,link):
  i=picker.get_selected();identifier=readiness.PROGRAMS[key][i-1][0] if 0<i<=len(readiness.PROGRAMS[key]) else None
  if identifier:self.programs[key]=identifier
  else:self.programs.pop(key,None)
  choice.set_sensitive(bool(identifier));choice.set_active(bool(identifier));link.set_visible(bool(identifier));self.update_selection()
 def choose_sharing(self):
  if self.app.setup_wizard and self.app.setup_wizard.window==self.window:
   self.app.setup_wizard.index=1;self.app.setup_wizard.refresh();return
  if self.app.software_window:self.app.software_window.close()
  self.app.show_settings()
  if self.app.section_stack:self.app.select_section('Applications')
 def choose_program(self,key):
  if self.checking:return
  self.app.file_dialog(lambda paths:self.test_program(key,str(paths[0])),multiple=False,parent=self.window)
 def choose_office(self):
  self.choose_program('office')
 def test_office(self,path):
  self.test_program('office',path)
 def test_program(self,key,path):
  if self.checking:return
  self.checking=True;self.office_button.set_sensitive(False);self.recheck.set_sensitive(False);self.install_button.set_sensitive(False);self.rows.set_sensitive(False);self.summary.set_text('Testing your chosen program for '+readiness.TITLES[key].lower()+'…');self.generation+=1;generation=self.generation
  def worker():
   try:row,overrides=readiness.check_program(key,path,self.values,self.cancel_check);error=None
   except Exception as e:row=None;overrides={};error=str(e)
   GLib.idle_add(self.program_tested,generation,key,path,row,overrides,error)
  threading.Thread(target=worker,daemon=True).start()
 def office_tested(self,generation,path,row,error):
  return self.program_tested(generation,'office',path,row,{},error)
 def program_tested(self,generation,key,path,row,overrides,error):
  if self.closed or generation!=self.generation:return False
  self.checking=False;self.office_button.set_sensitive(True);self.recheck.set_sensitive(True);self.rows.set_sensitive(True)
  if row and row.status=='ready':
   if self.save_program(key,path,overrides):self.message.set_text('Your selected program passed its checks and is now selected.');self.scan()
  else:
   detail=error or (row.detail if row else 'Could not test this program.')
   self.message.set_text('This program did not pass all required checks. '+detail+' Choose another program from the list or use Other program.');self.summary.set_text('Your program selection was not changed.');self.update_selection()
  return False
 def save_office(self,path):
  return self.save_program('office',path,{})
 def save_program(self,key,path,overrides):
  field='libreoffice_path' if key=='office' else 'engine_paths';previous=self.values.get(field);value=path if key=='office' else {**self.values.get('engine_paths',{}),**overrides}
  try:self.changed(field,value);return True
  except OSError as e:
   if previous is None:self.values.pop(field,None)
   else:self.values[field]=previous
   self.message.set_text('The program passed its checks, but your selection could not be saved: '+str(e));self.update_selection();return False
 def review(self):
  if self.checking or self.install_job:return
  keys=[k for k,b in self.choices.items() if b.get_active()]
  try:plan=readiness.install_plan(keys,programs=self.programs)
  except ValueError as e:self.message.set_text(str(e));return
  if self.review_window:self.review_window.present();return
  review=Gtk.ApplicationWindow(application=self.app,title='Review software installation');self.review_window=review;review.set_default_size(*fit_size(560,420));review.set_resizable(False);review.set_modal(True);review.set_transient_for(self.window)
  restore=bool(Layer and Layer.is_layer_window(self.window) and self.window.get_visible())
  if restore:self.window.set_visible(False)
  content=box(spacing=15);content.add_css_class('setup-root');review.set_child(content);content.append(label('Ready to download?','title'));content.append(label('From your configured Arch / CachyOS repositories:','muted',True))
  for key in plan['features']:content.append(label(readiness.TITLES[key]+' · '+plan['programs'][key],wrap=True))
  content.append(label('Your system installer will show the total download, any dependencies, and a final confirmation. It may request your password. Repository refreshes, system upgrades, and forced installs are not performed. If installation fails, you can use your usual software manager.','muted',True))
  row=box(Gtk.Orientation.HORIZONTAL,8);content.append(row)
  def close(*_):
   self.review_window=None;review.destroy()
   if restore:self.window.present()
   return True
  def install():close();self.start_install(plan)
  row.append(button('Cancel',close));self.confirm_install_button=button('Download and install',install,'primary');row.append(self.confirm_install_button);review.connect('close-request',close);review.present()
 def start_install(self,plan):
  try:
   # Rebuild from the selected feature IDs, never from editable command text.
   plan=readiness.install_plan(plan['features'],programs=plan['programs']);job=self.app.state/'installations'/uuid.uuid4().hex;job.mkdir(parents=True);path=job/'plan.json';path.write_text(json.dumps(plan))
   payload=[sys.executable,str(Path(__file__).with_name('install_helper.py')),str(path)]
   integrations.launch_terminal(self.values,Path.home(),payload)
  except Exception as e:self.message.set_text('Could not open the installer: '+str(e)+'. Choose a terminal in Applications or use your software manager.');return
  self.install_job=job;self.install_features=plan['features'];self.install_started=time.monotonic();self.install_button.set_sensitive(False);self.message.set_text('The system installer is open in your terminal. Confirm there to download and install. Close the terminal to cancel.');GLib.timeout_add(1000,self.poll_install)
 def poll_install(self):
  if self.closed:return False
  if self.install_job is None:return False
  result=self.install_job/'result.json'
  if not result.exists():
   started=self.install_job/'started.json'
   if started.exists():
    try:pid=json.loads(started.read_text())['pid'];os.kill(pid,0)
    except ProcessLookupError:
     self.install_job=None;self.message.set_text('The installer closed before reporting success. Checking what is available…');self.scan();return False
    except (OSError,ValueError,KeyError):pass
   elif time.monotonic()-self.install_started>90:
    self.install_job=None;self.message.set_text('The terminal did not start the installer. Choose another terminal in Applications, or use your software manager.');self.update_selection();return False
   return True
  try:data=json.loads(result.read_text())
  except (OSError,ValueError):return True
  self.install_job=None
  if data.get('success') and 'office' in self.install_features:self.pending_office=shutil.which('libreoffice') or shutil.which('soffice')
  self.message.set_text(data['message']);self.scan();return False

class SoftwareWindow:
 def __init__(self,app):
  self.window=Gtk.ApplicationWindow(application=app,title='Petal · Software check');self.window.set_default_size(*fit_size(800,760));self.window.set_resizable(False);self.page=SoftwarePage(app,self.window,app.settings,app.setting)
  root=box(spacing=10);root.add_css_class('setup-root');scroll=Gtk.ScrolledWindow();scroll.set_policy(Gtk.PolicyType.AUTOMATIC,Gtk.PolicyType.AUTOMATIC);scroll.set_child(self.page);scroll.set_vexpand(True);root.append(scroll);root.append(button('Close',self.close));self.window.set_child(root);self.window.connect('close-request',self.close)
  self.restore=bool(app.controls and app.controls.get_visible());
  if app.controls:app.controls.set_visible(False)
  if app.main:app.main.set_visible(False)
  self.app=app;self.window.present()
 def close(self,*_):
  self.page.dispose_page()
  if self.page.review_window:self.page.review_window.destroy()
  self.window.destroy();self.app.software_window=None
  if self.restore and self.app.controls:self.app.refresh_engine_status();self.app.controls.present()
  return True
