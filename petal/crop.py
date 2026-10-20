"""Image-space crop selection shared by pointer handles and precise fields."""
import io
import math
import cairo
from PIL import Image,ImageOps
from .legacy import Gtk

class CropCanvas(Gtk.DrawingArea):
 def __init__(self,path,changed,pixel_step=1):
  super().__init__();self.changed=changed;self.pixel_step=pixel_step
  with Image.open(path) as source:
   image=ImageOps.exif_transpose(source).convert('RGBA');self.image_width,self.image_height=image.size
   image.thumbnail((1100,850));data=io.BytesIO();image.save(data,format='PNG')
  self.surface=cairo.ImageSurface.create_from_png(io.BytesIO(data.getvalue()))
  self.rect=(0,0,self.image_width-self.image_width%pixel_step,self.image_height-self.image_height%pixel_step);self.gesture_mode=None
  self.set_content_width(560);self.set_content_height(250);self.set_hexpand(True);self.set_draw_func(self.draw)
  self.update_property([Gtk.AccessibleProperty.LABEL,Gtk.AccessibleProperty.DESCRIPTION],['Rectangle selection','Drag handles to resize, or edit the coordinate fields below.'])
  self.set_tooltip_text('Drag to select. Drag inside to move; drag a handle to resize.')
  drag=Gtk.GestureDrag();drag.connect('drag-begin',self.drag_begin);drag.connect('drag-update',self.drag_update);drag.connect('drag-end',self.drag_end);self.add_controller(drag)
 def transform(self):
  width=max(1,self.get_width());height=max(1,self.get_height());scale=min(width/self.image_width,height/self.image_height)
  return scale,(width-self.image_width*scale)/2,(height-self.image_height*scale)/2
 def image_point(self,x,y):
  scale,ox,oy=self.transform();return max(0,min(self.image_width,(x-ox)/scale)),max(0,min(self.image_height,(y-oy)/scale))
 def set_rect(self,x,y,width,height,notify=False):
  if not all(math.isfinite(v) for v in (x,y,width,height)):raise ValueError('Enter finite crop values.')
  x,y,width,height=(int(v)//self.pixel_step*self.pixel_step for v in (x,y,width,height))
  if not all(math.isfinite(v) for v in (x,y,width,height)) or x<0 or y<0 or width<1 or height<1 or x+width>self.image_width or y+height>self.image_height:raise ValueError('Keep the crop rectangle inside the image with a width and height of at least one pixel.')
  self.rect=tuple(round(v) for v in (x,y,width,height));self.queue_draw()
  if notify:self.changed(*self.rect)
 def handles(self):
  x,y,w,h=self.rect
  return {'nw':(x,y),'n':(x+w/2,y),'ne':(x+w,y),'e':(x+w,y+h/2),'se':(x+w,y+h),'s':(x+w/2,y+h),'sw':(x,y+h),'w':(x,y+h/2)}
 def drag_begin(self,gesture,x,y):
  self.origin=(x,y);self.start_point=self.image_point(x,y);self.start_rect=self.rect
  px,py=self.start_point;scale,_,_=self.transform();radius=10/scale
  self.gesture_mode=next((name for name,(hx,hy) in self.handles().items() if math.hypot(px-hx,py-hy)<=radius),None)
  rx,ry,rw,rh=self.rect
  if self.gesture_mode is None:self.gesture_mode='move' if 0<rw<self.image_width and 0<rh<self.image_height and rx<=px<=rx+rw and ry<=py<=ry+rh else 'new'
 def drag_update(self,gesture,dx,dy):
  if not self.gesture_mode:return
  px,py=self.image_point(self.origin[0]+dx,self.origin[1]+dy);sx,sy=self.start_point;x,y,w,h=self.start_rect;mode=self.gesture_mode
  if mode=='move':
   self.set_rect(max(0,min(self.image_width-w,x+px-sx)),max(0,min(self.image_height-h,y+py-sy)),w,h,True);return
  if mode=='new':left,right=sorted((sx,px));top,bottom=sorted((sy,py))
  else:
   left,top,right,bottom=x,y,x+w,y+h
   if 'w' in mode:left=min(px,right-1)
   if 'e' in mode:right=max(px,left+1)
   if 'n' in mode:top=min(py,bottom-1)
   if 's' in mode:bottom=max(py,top+1)
  left=max(0,min(self.image_width-1,round(left)));top=max(0,min(self.image_height-1,round(top)))
  right=max(left+1,min(self.image_width,round(right)));bottom=max(top+1,min(self.image_height,round(bottom)))
  self.set_rect(left,top,right-left,bottom-top,True)
 def drag_end(self,gesture,dx,dy):self.drag_update(gesture,dx,dy);self.gesture_mode=None
 def draw(self,area,c,width,height):
  scale,ox,oy=self.transform();c.set_source_rgb(.09,.09,.1);c.paint();c.save();c.translate(ox,oy);c.scale(scale,scale)
  c.save();c.scale(self.image_width/self.surface.get_width(),self.image_height/self.surface.get_height());c.set_source_surface(self.surface);c.paint();c.restore()
  x,y,w,h=self.rect;c.set_source_rgba(0,0,0,.55)
  for xx,yy,ww,hh in [(0,0,self.image_width,y),(0,y,x,h),(x+w,y,self.image_width-x-w,h),(0,y+h,self.image_width,self.image_height-y-h)]:c.rectangle(xx,yy,ww,hh);c.fill()
  c.rectangle(x,y,w,h);c.set_source_rgb(1,.36,.04);c.set_line_width(2/scale);c.stroke();c.set_source_rgba(1,1,1,.45);c.set_line_width(1/scale)
  for fraction in (1/3,2/3):
   c.move_to(x+w*fraction,y);c.line_to(x+w*fraction,y+h);c.move_to(x,y+h*fraction);c.line_to(x+w,y+h*fraction)
  c.stroke()
  for hx,hy in self.handles().values():c.rectangle(hx-4/scale,hy-4/scale,8/scale,8/scale);c.set_source_rgb(1,1,1);c.fill()
  c.restore()
