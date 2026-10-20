"""Borderless conversion wheel; a hovered petal expands and turns orange."""
import math
import cairo

ORANGE=(1,.36,.025);INK=(.12,.13,.14);MUTED=(.46,.47,.49);WHITE=(1,1,1)
PETAL=(1,1,1);PETAL_ALPHA=.66;HOVER_INK=WHITE
FONT='Arial'

def lerp(a,b,t):return tuple(x+(y-x)*t for x,y in zip(a,b))

def text(c,s,x,y,size=12,color=INK,bold=False,center=True):
 c.select_font_face(FONT,cairo.FONT_SLANT_NORMAL,cairo.FONT_WEIGHT_BOLD if bold else cairo.FONT_WEIGHT_NORMAL)
 c.set_font_size(size);c.set_source_rgb(*color);e=c.text_extents(s)
 c.move_to(x-e.width/2-e.x_bearing if center else x,y);c.show_text(s)

def geometry(w,h):return w/2,h/2,min(w,h)*.365,min(w,h)*.137
def hit(x,y,w,h,count,selected=-1,expansions=None):
 if not count or w<=0 or h<=0:return -1
 cx,cy,r,inner=geometry(w,h);step=math.tau/count;values=expansions or {}
 # Test the painted path, including its current expansion and rounded gaps.
 surface=cairo.RecordingSurface(cairo.CONTENT_ALPHA,None);c=cairo.Context(surface)
 order=([selected] if 0<=selected<count else [])+[i for i in range(count) if i!=selected]
 for i in order:
  mid=-math.pi/2+i*step;ax,ay=point(cx,cy,inner,mid);scale=1+values.get(i,0)*.14
  px=ax+(x-ax)/scale;py=ay+(y-ay)/scale
  segment(c,cx,cy,r,inner,mid-step/2+.018,mid+step/2-.018)
  if c.in_fill(px,py):return i
 return -1
def point(cx,cy,r,a):return cx+math.cos(a)*r,cy+math.sin(a)*r
def quadratic(c,control,end):
 x,y=c.get_current_point();qx,qy=control;ex,ey=end
 c.curve_to(x+2*(qx-x)/3,y+2*(qy-y)/3,ex+2*(qx-ex)/3,ey+2*(qy-ey)/3,ex,ey)
def segment(c,cx,cy,outer,inner,a,b,corner=12):
 oa=corner/outer;ia=min(corner/inner,(b-a)*.22)
 c.new_path();c.move_to(*point(cx,cy,outer,a+oa));c.arc(cx,cy,outer,a+oa,b-oa)
 quadratic(c,point(cx,cy,outer,b),point(cx,cy,outer-corner,b))
 c.line_to(*point(cx,cy,inner+corner,b));quadratic(c,point(cx,cy,inner,b),point(cx,cy,inner,b-ia))
 c.arc_negative(cx,cy,inner,b-ia,a+ia);quadratic(c,point(cx,cy,inner,a),point(cx,cy,inner+corner,a))
 c.line_to(*point(cx,cy,outer-corner,a));quadratic(c,point(cx,cy,outer,a),point(cx,cy,outer,a+oa));c.close_path()

# Original line artwork, following the reference tool symbols.
def tool_icon(c,id,x,y,color):
 c.save();c.translate(x,y);c.set_source_rgb(*color);c.set_line_width(1.65);c.set_line_cap(cairo.LINE_CAP_ROUND);c.set_line_join(cairo.LINE_JOIN_ROUND)
 if id in ('crop','resize'):
  c.move_to(-5,-10);c.line_to(-5,5);c.line_to(10,5);c.move_to(-10,-5);c.line_to(5,-5);c.line_to(5,10);c.stroke()
 elif id=='redact':
  c.move_to(-11,0);c.curve_to(-4,-9,4,-9,11,0);c.curve_to(4,9,-4,9,-11,0);c.stroke();c.arc(0,0,3,0,math.tau);c.stroke()
  c.move_to(-10,-10);c.line_to(10,10);c.stroke()
 elif id in ('compress','pdf_compress'):
  for sign in (-1,1):
   c.move_to(sign*9,sign*-9);c.line_to(sign*2,sign*-2);c.line_to(sign*2,sign*-8);c.move_to(sign*2,sign*-2);c.line_to(sign*8,sign*-2)
  c.stroke()
 elif id in ('edit','volume','channels','normalize','speed'):
  for yy,xx in [(-7,4),(0,-4),(7,2)]:
   c.move_to(-10,yy);c.line_to(xx-2,yy);c.move_to(xx+2,yy);c.line_to(10,yy);c.stroke();c.arc(xx,yy,2,0,math.tau);c.stroke()
 elif id=='annotate':
  c.arc(0,0,9,.4,math.tau-1);c.stroke();c.move_to(-4,4);c.line_to(-2,-1);c.line_to(7,-10);c.line_to(10,-7);c.line_to(1,2);c.close_path();c.stroke()
 elif id in ('strip','metadata'):
  c.move_to(-10,0);c.line_to(0,-10);c.line_to(8,-10);c.line_to(10,-8);c.line_to(10,0);c.line_to(0,10);c.close_path();c.stroke();c.arc(5,-5,1.4,0,math.tau);c.stroke()
 elif id in ('background','collage','snapshots'):
  c.rectangle(-10,-8,20,16);c.stroke();c.rectangle(-7,-5,14,10);c.stroke();c.move_to(-6,4);c.line_to(-1,-1);c.line_to(2,2);c.line_to(5,-2);c.line_to(7,2);c.stroke();c.arc(-3,-2,1,0,math.tau);c.fill()
 elif id in ('trim','bleep'):
  for xx,hh in [(-9,3),(-6,6),(-3,9),(0,5),(3,8),(6,6),(9,2)]:c.move_to(xx,-hh);c.line_to(xx,hh)
  c.stroke()
 elif id in ('copy','copy_path'):
  rounded(c,-8,-8,13,16,2);c.stroke();c.move_to(7,-4);c.line_to(10,-4);c.line_to(10,11);c.line_to(-2,11);c.stroke()
 elif id in ('share','shelf','move','terminal'):
  c.move_to(-9,1);c.line_to(-9,9);c.line_to(9,9);c.line_to(9,1);c.move_to(0,4);c.line_to(0,-10);c.move_to(-5,-5);c.line_to(0,-10);c.line_to(5,-5);c.stroke()
 else:
  rounded(c,-8,-10,16,20,2);c.stroke();c.move_to(-4,-3);c.line_to(4,-3);c.move_to(-4,2);c.line_to(4,2);c.stroke()
 c.restore()

TOOL_NAMES={'edit':'EDIT','background':'ADD BG','annotate':'ANNOTATE','crop':'CROP','redact':'REDACT','strip':'METADATA','compress':'COMPRESS'}

def draw(c,w,h,items,selected=-1,title='',subtitle='',mode='convert',expansions=None,page_text='',thumbnail=None):
 cx,cy,r,inner=geometry(w,h);n=len(items);values=expansions or {}
 if n:
  step=math.tau/n;gap=.018
  order=[i for i in range(n) if i!=selected]+([selected] if 0<=selected<n else [])
  for i in order:
   value=values.get(i,0.0);mid=-math.pi/2+i*step
   anchor=point(cx,cy,inner,mid);scale=1+value*.14
   c.save();c.translate(anchor[0],anchor[1]);c.scale(scale,scale);c.translate(-anchor[0],-anchor[1])
   segment(c,cx,cy,r,inner,mid-step/2+gap,mid+step/2-gap)
   c.set_source_rgba(*lerp(PETAL,ORANGE,value),PETAL_ALPHA+(1-PETAL_ALPHA)*value);c.fill_preserve()
   c.set_source_rgba(0,0,0,.10*(1-value));c.set_line_width(.6);c.stroke()
   x,y=point(cx,cy,(r+inner)/2,mid);color=lerp(INK,HOVER_INK,value)
   if mode=='convert':text(c,item_label(items[i]),x,y+4,12,color,True)
   else:
    tool_icon(c,items[i].id,x,y-6,color)
    name=TOOL_NAMES.get(items[i].id,item_label(items[i]).upper()).replace('REMOVE ','').replace(' / SHELF','').replace('ADD TEXT','ANNOTATE')
    words=name.split();lines=[name] if len(name)<=11 else [' '.join(words[:max(1,len(words)//2)]),' '.join(words[max(1,len(words)//2):])]
    for j,line in enumerate(lines):text(c,line,x,y+15+j*9,7.5 if n>8 else 8.5,color,True)
   c.restore()
 # The center stays transparent; the file-size pill overlays its thumbnail.
 if thumbnail is not None:
  tw,th=thumbnail.get_width(),thumbnail.get_height();scale=min((inner*1.25)/tw,(inner*1.35)/th)
  dw,dh=tw*scale,th*scale
  c.save();rounded(c,cx-dw/2,cy-dh/2-5,dw,dh,5);c.clip();c.translate(cx-dw/2,cy-dh/2-5);c.scale(scale,scale);c.set_source_surface(thumbnail);c.paint();c.restore()
 elif not title:
  tool_icon(c,'background',cx,cy-9,INK)
 center=title or 'Drop file'
 c.save();c.select_font_face(FONT,cairo.FONT_SLANT_NORMAL,cairo.FONT_WEIGHT_NORMAL);c.set_font_size(11);e=c.text_extents(center)
 pw=max(62,min(inner*2+12,e.width+24));py=cy+3 if thumbnail is not None else cy-13
 rounded(c,cx-pw/2,py,pw,29,14.5);c.set_source_rgba(*PETAL,.76);c.fill()
 text(c,center,cx,py+19,11,INK,True)
 if page_text:text(c,page_text,cx,cy+40,7.5,INK)
 c.restore()

def item_label(item):
 return getattr(item,'label',str(item))

def rounded(c,x,y,w,h,r):
 c.new_sub_path()
 for cx,cy,a in [(x+w-r,y+r,-math.pi/2),(x+w-r,y+h-r,0),(x+r,y+h-r,math.pi/2),(x+r,y+r,math.pi)]:c.arc(cx,cy,r,a,a+math.pi/2)
 c.close_path()

def sample_wallpaper(c,w,h):
 gradient=cairo.LinearGradient(0,0,w,h);gradient.add_color_stop_rgb(0,1,.54,.11);gradient.add_color_stop_rgb(.48,1,.37,.28);gradient.add_color_stop_rgb(1,.68,.66,.87);c.set_source(gradient);c.paint()
 glow=cairo.RadialGradient(w*.60,h*.02,0,w*.60,h*.02,w*.65);glow.add_color_stop_rgba(0,1,.82,0,1);glow.add_color_stop_rgba(.5,1,.67,.02,.7);glow.add_color_stop_rgba(1,1,.52,.06,0);c.set_source(glow);c.paint()

def preview(path):
 from .catalog import Action,TOOLS
 surface=cairo.ImageSurface(cairo.FORMAT_ARGB32,1000,620);c=cairo.Context(surface);sample_wallpaper(c,1000,620)
 text(c,'Petal',500,55,24,INK,True)
 text(c,'Desktop overlay · reference proportions, translucent petals, independent hover animation',500,84,12,INK)
 for x,mode,items,title,selected in [(70,'convert',[Action('to:'+f,f.upper()) for f in ['jpg','webp','heic','tiff','avif','bmp','pdf','docx']],'Conversions',1),(570,'tools',TOOLS['image'][:7],'Tools',3)]:
  c.save();c.translate(x,130);draw(c,360,360,items,selected,'2.2 MB',mode=mode,expansions={selected:1.0});c.restore();text(c,title,x+180,536,15,INK,True)
 text(c,'Shown over a sample wallpaper. The app surfaces are transparent.',500,588,11,INK)
 surface.write_to_png(str(path))

def app_icon(c,size):
 """Simple native fallback when the shipped Petal logo cannot be loaded."""
 c.save();c.scale(size/100,size/100)
 for i in range(6):
  c.save();c.translate(50,50);c.rotate(i*math.tau/6)
  c.move_to(0,-45);c.curve_to(27,-29,33,-6,10,9);c.curve_to(5,-8,-19,-13,0,-45)
  c.set_source_rgb(*(ORANGE if i%2==0 else (.94,.27,.20)));c.fill();c.restore()
 c.restore()
