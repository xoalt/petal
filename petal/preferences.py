"""App-local preferences. No desktop defaults or compositor rules are changed."""
import re

DEFAULTS={
 'setup_completed':False,'setup_version':0,
 'file_manager':'','terminal_app':'','sharing_app':'','image_app':'','media_app':'','document_app':'',
 'engine_paths':{},
 'quality':85,'dpi':150,'notify':True,'drop_target':True,'tray_enabled':True,'output_dir':'',
 'appearance_mode':'light','accent_color':'#ff5300','petal_color':'#ffffff','text_color':'#202124','petal_opacity':66,'animations':True,
}
PRESETS={
 'Orange':('#ff5300','#ffffff','#202124'),
 'Ocean':('#1678d2','#edf6ff','#18344c'),
 'Forest':('#287b50','#edf7ef','#203e2b'),
 'Lavender':('#845bd4','#f4efff','#35274b'),
 'Rose':('#c94476','#fff0f5','#4c2836'),
 'Graphite':('#515a67','#edf0f4','#222832'),
}
APP_ROLES=[('file_manager','File manager','Used to show converted files and folders.'),('terminal_app','Terminal','Used by Open Terminal and terminal file managers.'),('sharing_app','Sharing app','Used by Share on the actions wheel.'),('image_app','Image app','Used when opening selected images.'),('media_app','Media player','Used when opening audio and video.'),('document_app','Document app','Used when opening PDFs and documents.')]
COLOR_KEYS=('accent_color','petal_color','text_color')

def color(value,default):return value.lower() if isinstance(value,str) and re.fullmatch(r'#[0-9a-fA-F]{6}',value) else default

def normalize(settings):
 result=dict(settings)
 for key,default in DEFAULTS.items():
  value=result.get(key,default)
  if key in COLOR_KEYS:value=color(value,default)
  elif key in ('setup_completed','animations','notify','drop_target','tray_enabled'):value=value if isinstance(value,bool) else default
  elif key in ('quality','dpi'):
   try:value=max(1 if key=='quality' else 36,min(100 if key=='quality' else 600,int(value)))
   except (ValueError,TypeError,OverflowError):value=default
  elif key=='petal_opacity':
   try:value=max(35,min(100,int(value)))
   except (ValueError,TypeError,OverflowError):value=default
  elif key=='appearance_mode':value=value if value in ('light','dark','system') else default
  elif key=='setup_version':value=value if isinstance(value,int) and not isinstance(value,bool) else default
  elif key=='engine_paths':value={k:v for k,v in value.items() if isinstance(k,str) and isinstance(v,str)} if isinstance(value,dict) else {}
  else:value=value if isinstance(value,str) else default
  result[key]=value
 return result

def rgb(value):return tuple(int(value[i:i+2],16)/255 for i in (1,3,5))

def readable_ink(value,reference=True):
 if reference and value.lower()==DEFAULTS['accent_color']:return (1,1,1)
 channels=rgb(value);linear=[v/12.92 if v<=.04045 else ((v+.055)/1.055)**2.4 for v in channels]
 luminance=sum(v*w for v,w in zip(linear,(.2126,.7152,.0722)))
 return ((0.10,.11,.12) if reference else (0,0,0)) if luminance>.179 else (1,1,1)
