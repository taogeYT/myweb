import re, time, json, logging, hashlib, base64, asyncio
from coroweb import get, post
from models import Test,User,Blog,Comment,next_id
from apis import *
from default import cfg
from aiohttp import web
import markdown2
#测试
@get('/test')
async def test(request):
	users = await Test.find_all()
	print(users)
	return {'__template__': 'test.html','users': users}
#API测试
# @get('/api/users')
# def api_get(*,page='1'):
	# users = yield from User.find_all(order_by='created_at desc')
	# print(users.encode())
	# return dict(users=users)
@get('/api/users')
async def api_get_users(*, page='1'):
    page_index = get_page_index(page)
    num = await User.find_number('id')
    p = Page(num, page_index)
    if num == 0:
        return dict(page=p, users=())
    users = await User.find_all(order_by='created_at desc', limit=(p.offset, p.limit))
    for u in users:
        u.passwd = '******'
    return dict(page=p, users=users)

COOKIE_NAME = 'awesome'
KEY = 'key'
def user2cookie(user,lease):
	expire_time = str(int(time.time()) + lease)
	s = '%s%s%s%s' %(user.id,user.passwd,expire_time,KEY)   #cookie生成公式
	l = [user.id,expire_time,hashlib.md5(s.encode('utf-8')).hexdigest()]
	return '-'.join(l)

async def cookie2user(cookie_str):
	if not cookie_str:
		return None
	try:
		l = cookie_str.split('-')
		if len(l) != 3:
			return None
		uid,expire_time,sha1 = l
		if int(expire_time) < time.time():
			return None
		user = await User.find(uid)
		if not user:
			return None
		s = '%s%s%s%s' %(uid,user.passwd,expire_time,KEY)
		if hashlib.md5(s.encode('utf-8')).hexdigest() != sha1:
			return None
		user.passwd = '******'
		return user
	except Exception as e:
		logging.exception(e)
		return None

@get('/')
async def index(*,page='1'):
	page_index = get_page_index(page)
	num = await Blog.find_number('id')
	p = Page(num,page_index)
	if num == 0:
		blogs = []
	else:
		blogs = await Blog.find_all(limit = (p.offset,p.limit))
	return {
		'__template__': 'blogs.html',
		'blogs': blogs,
		'page':p
	}

@get('/register')
def register():
	return {'__template__':'register.html'}

_RE_EMAIL = re.compile(r'^[a-z0-9\.\-\_]+\@[a-z0-9\-\_]+(\.[a-z0-9\-\_]+){1,4}$')
_RE_SHA1 = re.compile(r'^[0-9a-f]{40}$')
@post('/api/users')
async def api_register_user(*,email,name,passwd):
	if not name or not name.strip():    #s.strip(rm)        删除 s字符串中 开头、结尾处 匹配到删除序列rm 的字符
		raise APIValueError('name')
	if not email or not _RE_EMAIL.match(email):
		raise APIValueError('email')
	if not passwd or not _RE_SHA1.match(passwd):
		raise APIValueError('password')
	users = await User.find_all('email=?',[email])
	if len(users) > 0:
		raise APIError('register:failed', 'email', 'Email is already in use.')
	uuid = next_id()
	sha1_passwd = '%s=>%s'%(uuid,passwd)  #密码加密公式
	user = User(id=uuid,email=email,name=name.strip(),passwd=hashlib.sha1(sha1_passwd.encode('utf-8')).hexdigest(),image='')  #摘要算法输入的是字节串
	await user.save()
	#make session cookie:
	r = web.Response()
	r.set_cookie(COOKIE_NAME,user2cookie(user,300),max_age=300,httponly=True) #如果您在cookie中设置了HttpOnly属性，那么通过js脚本将无法读取到cookie信息，这样能有效的防止XSS攻击
	user.passwd = '******'
	r.content_type = 'application/json'
	r.body = json.dumps(user,ensure_ascii=False).encode('utf-8')  #ensure_ascii 表示转换为json格式时字符串内容全部当作ascii转换
	return r

@get('/signin')
def signin():
	return {'__template__':'signin.html'}

@get('/signout')
def signout(request):
	referer = request.headers.get('Referer')
	r = web.HTTPFound(referer or '/')                                #状态码302 Found重定向
	r.set_cookie(COOKIE_NAME, '-deleted-', max_age=0, httponly=True) #删除浏览器cookie
	logging.info('user signed out.')
	return r

@post('/api/authenticate')
async def authenticate(*,email,passwd):
	if not email:
		raise APIValueError('email','Invalid email')
	if not passwd:
		raise APIValueError('password','Invalid password')
	users = await User.find_all('email=?',email)
	if len(users)==0:
		raise APIValueError('email','Email not exist')
	user = users[0]
	#check password
	sha1 = hashlib.sha1()
	sha1.update(user.id.encode('utf-8'))
	sha1.update(b'=>')
	sha1.update(passwd.encode('utf-8'))
	if sha1.hexdigest() != user.passwd:
		raise APIValueError('password','password error')
	# authenticate ok, set cookie:
	r = web.Response()
	r.set_cookie(COOKIE_NAME,user2cookie(user,300),max_age=300,httponly=True)
	r.body = json.dumps(user,ensure_ascii=False).encode('utf-8') #json格式是一个字符串
	return r

@get('/manage/blogs/create')
def manage_create_blog():
	return {'__template__': 'manage_blog_edit.html','id': '','action': '/api/blogs'}

def check_admin(request):
	if request.__user__ is None or not request.__user__.admin:
		raise APIPermissionError()

@post('/api/blogs')
async def api_create_blog(request,*,name,summary,content):
	if request.__user__ is None: #or not request.__user__.admin:
		raise APIPermissionError()
	if not name or not name.strip():
		raise APIValueError('name')
	if not summary or not summary.strip():
		raise APIValueError('summary')
	if not content or not content.strip():
		raise APIValueError('content')
	blog = Blog(user_id=request.__user__.id,user_name=request.__user__.name,user_image=request.__user__.image,name=name.strip(),summary=summary.strip(),content=content.strip())
	await blog.save()
	return blog

def get_page_index(page_str):
	p = 1
	try:
		p = int(page_str)
	except:
		pass
	if p < 1:
		p = 1
	return p

#返回model给view网页显示日志列表
@get('/api/blogs')
async def api_blogs(*,page='1'):
	page_index = get_page_index(page)
	item_count = await Blog.find_number('id')
	p = Page(item_count,page_index)
	if item_count == 0:
		return dict(page=p,blogs=())
	blogs = await Blog.find_all(order_by='created_at desc',limit=(p.offset,p.limit))
	return dict(page=p,blogs=blogs)

@get('/manage/blogs')
def manage_blogs(*, page='1'):
	return {
		'__template__': 'manage_blogs.html',
		'page_index': get_page_index(page)
	}

@get('/api/blogs/{id}')
def api_get_blog(*, id):
	blog = yield from Blog.find(id)
	return blog

def text2html(text):
    lines = map(lambda s: '<p>%s</p>' % s.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;'), filter(lambda s: s.strip() != '', text.split('\n')))
    return ''.join(lines)

@get('/blog/{id}')
def get_blog(id):
	blog = yield from Blog.find(id)
	comments = yield from Comment.find_all('blog_id=?', [id], order_by='created_at desc')
	for c in comments:
		c.html_content = text2html(c.content)
	blog.html_content = markdown2.markdown(blog.content)
	return {
		'__template__': 'blog.html',
		'blog': blog,
		'comments': comments
	}

@get('/manage/')
def manage():
	return 'redirect:/manage/comments'

@get('/api/comments')
async def api_comments(*, page='1'):
    page_index = get_page_index(page)
    num = await Comment.find_number('id')
    p = Page(num, page_index)
    if num == 0:
        return dict(page=p, comments=())
    comments = await Comment.find_all(order_by='created_at desc', limit=(p.offset, p.limit))
    return dict(page=p, comments=comments)

@get('/manage/comments')
def manage_comments(*, page='1'):
    return {
        '__template__': 'manage_comments.html',
        'page_index': get_page_index(page)
    }

@get('/manage/users')
def manage_users(*, page='1'):
    return {
        '__template__': 'manage_users.html',
        'page_index': get_page_index(page)
    }


