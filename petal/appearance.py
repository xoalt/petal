"""Appearance shared by setup, Settings, the wheel, and editor controls."""
from .preferences import normalize,rgb,readable_ink
from . import wheel

def stylesheet(base,settings,system_dark=False):
 p=normalize(settings);accent=p['accent_color'];dark=p['appearance_mode']=='dark' or (p['appearance_mode']=='system' and system_dark)
 css=base+'\npopover contents {background:#fafafa;color:#202124;}\n'
 for original in ('#ff5300','#ff6109','#e85b08'):css=css.replace(original,accent)
 if dark:
  css+='''
window {background:#1d2026;color:#edf0f6;}
window.layer,window.wheel-surface,window.tool-window {background:transparent;}
.setup-root,.panel,.settings-body {background:#1d2026;color:#edf0f6;border-color:#414754;}
.sidebar {background:#282d36;color:#edf0f6;}
.muted,.hint {color:#aeb7c6;}
button {background:#303642;color:#edf0f6;border-color:#454d5b;}
button:hover,button:checked {background:#414957;}
entry,dropdown,spinbutton,popover contents {background:#282e38;color:#edf0f6;border-color:#4c5666;}
.status {background:#282e38;border-color:#414957;}
.material-shell {background:rgba(29,33,41,.90);color:#edf0f6;border-color:#596273;}
.tool-window {color:#edf0f6;}
.tool-window button {background:rgba(255,255,255,.12);color:#edf0f6;}
.tool-window entry,.tool-window spinbutton {background:rgba(255,255,255,.09);color:#edf0f6;}
.tool-window .hint,.tool-window .reset-control {color:#b8c2d3;}
.setup-card,.theme-preview {background:#282e38;border-color:#414957;}
.success {color:#89d1a6;} .error {color:#ffb4a7;}
'''
 css+='\nbutton.primary,.tool-window button.primary,switch:checked,.tool-window scale highlight,.tool-window progressbar progress {background:'+accent+';border-color:'+accent+';}\n'
 css+='.orange {color:'+accent+';}\n'
 ink='#'+''.join(f'{round(v*255):02x}' for v in readable_ink(accent,reference=False))
 css+='button.primary,.tool-window button.primary {color:'+ink+';} button:focus-visible {outline:2px solid currentColor;outline-offset:2px;}\n'
 css+='button.primary:disabled {background:'+('#353b46' if dark else '#e0e2e5')+';border-color:'+('#353b46' if dark else '#e0e2e5')+';color:'+('#929baa' if dark else '#777b82')+';}\n'
 return css

def apply_wheel(settings):
 p=normalize(settings);wheel.ORANGE=rgb(p['accent_color']);wheel.PETAL=rgb(p['petal_color']);wheel.INK=rgb(p['text_color']);wheel.PETAL_ALPHA=p['petal_opacity']/100;wheel.HOVER_INK=readable_ink(p['accent_color'])
