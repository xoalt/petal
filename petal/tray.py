"""StatusNotifierItem + DBusMenu, usable by Noctalia without GTK3/AppIndicator."""
import array
import cairo
from pathlib import Path
from gi.repository import Gio,GLib

SNI='org.kde.StatusNotifierItem'
MENU='com.canonical.dbusmenu'
XML='''<node>
<interface name="org.kde.StatusNotifierItem">
 <method name="Activate"><arg type="i" direction="in"/><arg type="i" direction="in"/></method>
 <method name="SecondaryActivate"><arg type="i" direction="in"/><arg type="i" direction="in"/></method>
 <method name="ContextMenu"><arg type="i" direction="in"/><arg type="i" direction="in"/></method>
 <method name="Scroll"><arg type="i" direction="in"/><arg type="s" direction="in"/></method>
 <property name="Category" type="s" access="read"/><property name="Id" type="s" access="read"/>
 <property name="Title" type="s" access="read"/><property name="Status" type="s" access="read"/>
 <property name="WindowId" type="u" access="read"/><property name="IconName" type="s" access="read"/>
 <property name="IconPixmap" type="a(iiay)" access="read"/><property name="IconThemePath" type="s" access="read"/>
 <property name="OverlayIconName" type="s" access="read"/><property name="OverlayIconPixmap" type="a(iiay)" access="read"/>
 <property name="AttentionIconName" type="s" access="read"/><property name="AttentionIconPixmap" type="a(iiay)" access="read"/>
 <property name="AttentionMovieName" type="s" access="read"/>
 <property name="ToolTip" type="(sa(iiay)ss)" access="read"/>
 <property name="ItemIsMenu" type="b" access="read"/><property name="Menu" type="o" access="read"/>
 <signal name="NewTitle"/><signal name="NewIcon"/><signal name="NewAttentionIcon"/>
 <signal name="NewOverlayIcon"/><signal name="NewToolTip"/><signal name="NewStatus"><arg type="s"/></signal>
</interface>
<interface name="com.canonical.dbusmenu">
 <method name="GetLayout"><arg type="i" direction="in"/><arg type="i" direction="in"/><arg type="as" direction="in"/><arg type="u" direction="out"/><arg type="(ia{sv}av)" direction="out"/></method>
 <method name="GetGroupProperties"><arg type="ai" direction="in"/><arg type="as" direction="in"/><arg type="a(ia{sv})" direction="out"/></method>
 <method name="GetProperty"><arg type="i" direction="in"/><arg type="s" direction="in"/><arg type="v" direction="out"/></method>
 <method name="Event"><arg type="i" direction="in"/><arg type="s" direction="in"/><arg type="v" direction="in"/><arg type="u" direction="in"/></method>
 <method name="EventGroup"><arg type="a(isvu)" direction="in"/><arg type="ai" direction="out"/></method>
 <method name="AboutToShow"><arg type="i" direction="in"/><arg type="b" direction="out"/></method>
 <method name="AboutToShowGroup"><arg type="ai" direction="in"/><arg type="ai" direction="out"/><arg type="ai" direction="out"/></method>
 <property name="Version" type="u" access="read"/><property name="TextDirection" type="s" access="read"/>
 <property name="Status" type="s" access="read"/><property name="IconThemePath" type="as" access="read"/>
 <signal name="LayoutUpdated"><arg type="u"/><arg type="i"/></signal>
 <signal name="ItemsPropertiesUpdated"><arg type="a(ia{sv})"/><arg type="a(ias)"/></signal>
</interface></node>'''

def icon_pixmap(size=32):
 surface=cairo.ImageSurface(cairo.FORMAT_ARGB32,size,size);c=cairo.Context(surface)
 asset=Path(__file__).resolve().parents[1]/'assets/petal.png'
 if asset.is_file():
  source=cairo.ImageSurface.create_from_png(str(asset));c.scale(size/source.get_width(),size/source.get_height());c.set_source_surface(source);c.get_source().set_filter(cairo.FILTER_BEST);c.paint()
 else:
  from .wheel import app_icon
  app_icon(c,size)
 surface.flush();raw=bytes(surface.get_data());pixels=array.array('I');pixels.frombytes(raw)
 return bytes(channel for pixel in pixels for channel in [(pixel>>24)&255,(pixel>>16)&255,(pixel>>8)&255,pixel&255])

class Tray:
 def __init__(self,app):
  self.app=app;self.bus=Gio.bus_get_sync(Gio.BusType.SESSION,None);self.registered=False;self.error=None;self.revision=1
  self.node=Gio.DBusNodeInfo.new_for_xml(XML);self.pixmap=[(32,32,icon_pixmap())]
  self.ids=[]
  for path,iface in [('/StatusNotifierItem',SNI),('/Menu',MENU)]:
   self.ids.append(self.bus.register_object(path,self.node.lookup_interface(iface),self.method,self.prop,None))
  self.watch=Gio.bus_watch_name_on_connection(self.bus,'org.kde.StatusNotifierWatcher',Gio.BusNameWatcherFlags.NONE,self.appeared,self.vanished)
 def appeared(self,*_):
  self.bus.call('org.kde.StatusNotifierWatcher','/StatusNotifierWatcher','org.kde.StatusNotifierWatcher','RegisterStatusNotifierItem',GLib.Variant('(s)',('/StatusNotifierItem',)),None,Gio.DBusCallFlags.NONE,5000,None,self.register_done)
 def register_done(self,bus,result):
  try:bus.call_finish(result);self.registered=True;self.error=None
  except GLib.Error as e:self.error=str(e);print('Tray:',e,flush=True)
 def vanished(self,*_):self.registered=False
 def items(self):
  return {0:('Petal',None),1:('Settings',self.app.show_settings),2:('Open conversion wheel',self.app.show_main),
   3:('Floating drop target',self.app.toggle_drop_target),4:('File shelf',self.app.show_shelf),6:('Activity',self.app.show_activity),7:('Check software',self.app.show_software),5:('Quit Petal',self.app.request_quit)}
 def properties(self,id):
  props={'label':GLib.Variant('s',self.items().get(id,('',))[0]),'enabled':GLib.Variant('b',True),'visible':GLib.Variant('b',True)}
  if id==0:props['children-display']=GLib.Variant('s','submenu')
  if id==3:props.update({'toggle-type':GLib.Variant('s','checkmark'),'toggle-state':GLib.Variant('i',int(self.app.settings.get('drop_target',False)))})
  return props
 def layout(self,id=0,depth=-1):
  children=[GLib.Variant('(ia{sv}av)',(i,self.properties(i),[])) for i in self.items() if i] if id==0 and depth!=0 else []
  return (id,self.properties(id),children)
 def click(self,id):
  callback=self.items().get(id,('',None))[1]
  if callback:GLib.idle_add(lambda:(callback(),False)[1])
 def update(self):
  self.revision+=1;self.bus.emit_signal(None,'/Menu',MENU,'LayoutUpdated',GLib.Variant('(ui)',(self.revision,0)))
 def prop(self,bus,sender,path,iface,key):
  if iface==MENU:
   return {'Version':GLib.Variant('u',4),'TextDirection':GLib.Variant('s','ltr'),'Status':GLib.Variant('s','normal'),'IconThemePath':GLib.Variant('as',[])}.get(key)
  props={'Category':('s','ApplicationStatus'),'Id':('s','petal'),'Title':('s','Petal · local file tools'),'Status':('s','Active'),
   'WindowId':('u',0),'IconName':('s',''),'IconPixmap':('a(iiay)',self.pixmap),'IconThemePath':('s',''),
   'OverlayIconName':('s',''),'OverlayIconPixmap':('a(iiay)',[]),'AttentionIconName':('s',''),'AttentionIconPixmap':('a(iiay)',[]),
   'AttentionMovieName':('s',''),'ToolTip':('(sa(iiay)ss)',('',self.pixmap,'Petal','Offline file conversion · right-click for Settings')),
   'ItemIsMenu':('b',False),'Menu':('o','/Menu')}
  return GLib.Variant(*props[key]) if key in props else None
 def method(self,bus,sender,path,iface,name,args,call):
  try:
   values=args.unpack()
   if iface==SNI:
    if name=='Activate':self.app.show_main()
    elif name in ('ContextMenu','SecondaryActivate'):self.app.show_settings()
    call.return_value(None);return
   if name=='GetLayout':call.return_value(GLib.Variant('(u(ia{sv}av))',(self.revision,self.layout(values[0],values[1]))))
   elif name=='GetGroupProperties':call.return_value(GLib.Variant('(a(ia{sv}))',([(i,self.properties(i)) for i in values[0]],)))
   elif name=='GetProperty':call.return_value(GLib.Variant('(v)',(self.properties(values[0]).get(values[1],GLib.Variant('s','')),)))
   elif name=='Event':
    if values[1]=='clicked':self.click(values[0])
    call.return_value(None)
   elif name=='EventGroup':
    for i,event,*_ in values[0]:
     if event=='clicked':self.click(i)
    call.return_value(GLib.Variant('(ai)',([],)))
   elif name=='AboutToShow':call.return_value(GLib.Variant('(b)',(False,)))
   elif name=='AboutToShowGroup':call.return_value(GLib.Variant('(aiai)',([],[])))
   else:call.return_dbus_error('org.freedesktop.DBus.Error.UnknownMethod',name)
  except Exception as e:call.return_dbus_error('org.freedesktop.DBus.Error.Failed',str(e))
 def close(self):
  Gio.bus_unwatch_name(self.watch)
  for id in self.ids:self.bus.unregister_object(id)
