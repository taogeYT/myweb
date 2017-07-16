from aiohttp import web
import functools
import inspect
import asyncio
import os
import logging
# log_format = '%(levelname)s %(filename)s %(message)s'
# logging.basicConfig(format=log_format, level=logging.INFO)
from urllib import parse
from aiohttp import web
from apis import *


def get(path):
    '''
    define decorator @post('/path')
    '''
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kw):
            return func(*args, **kw)
        wrapper.__method__ = 'GET'
        wrapper.__path__ = path
        return wrapper
    return decorator


def post(path):
    '''
    define decorator @post('/path')
    '''
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kw):
            return func(*args, **kw)
        wrapper.__method__ = 'POST'
        wrapper.__path__ = path
        return wrapper
    return decorator
# 获取必选参数


def get_required_kw_args(fun):
    args = []
    params = inspect.signature(fun).parameters
    for name, param in params.items():
        # if param.kind == inspect.Parameter.KEYWORD_ONLY and param.default ==
        # inspect.Parameter.empty:
        if param.kind == inspect.Parameter.empty:
            args.append(name)
    return tuple(args)
# 获取命名关键字参数


def get_named_kw_args(fun):
    args = []
    params = inspect.signature(fun).parameters
    for name, param in params.items():
        if param.kind == inspect.Parameter.KEYWORD_ONLY:
            args.append(name)
    return tuple(args)
# 是否有命名关键字参数


def has_named_kw_args(fun):
    params = inspect.signature(fun).parameters
    for name, param in params.items():
        if param.kind == inspect.Parameter.KEYWORD_ONLY:
            return True


def has_var_kw_arg(fun):
    params = inspect.signature(fun).parameters
    for name, param in params.items():
        if param.kind == inspect.Parameter.VAR_KEYWORD:
            return True


def has_request_arg(fun):
    params = inspect.signature(fun).parameters
    for name, param in params.items():
        if name == 'request':
            return True


class RequestHandler(object):

    def __init__(self, fun):
        self._fun = fun
        self._has_request_arg = has_request_arg(fun)
        self._has_var_kw_arg = has_var_kw_arg(fun)
        self._has_named_kw_args = has_named_kw_args(fun)
        self._named_kw_args = get_named_kw_args(fun)
        self._required_kw_args = get_required_kw_args(fun)

    async def __call__(self, request):
        kw = None
        if self._has_var_kw_arg or self._has_named_kw_args:
            if request.method == 'POST':
                if not request.content_type:
                    return web.HTTPBadRequest('content type missed')
                ct = request.content_type.lower()
                if ct.startswith('application/json'):
                    params = await request.json()
                    if not isinstance(params, dict):
                        return web.HTTPBadRequest('JSON body must be object.')
                    kw = params
                elif ct.startswith('application/x-www-form-urlencoded') or ct.startswith('multipart/form-data'):
                    params = await request.post()
                    kw = dict(params)
                else:
                    return web.HTTPBadRequest('Unsupported Content-Type: %s' % request.content_type)
            if request.method == 'GET':
                qs = request.query_string  # 返回的值是字符串，例如http://127.0.0.1:8000/signin?a=1 返回'a=1'
                if qs:
                    kw = dict()
                    # url中语法格式的处理方法，True表示a的值如果为空，a不会被忽略
                    for k, v in parse.parse_qs(qs, True).items():
                        kw[k] = v[0]
        if kw is None:
            # match_info 是一个字典存储带参数url中的变量及其实际请求的url的值 如：｛'name':yt｝
            # @get('/{name}')
            kw = dict(**request.match_info)
            # return await self._fun(*kw.values())
        else:
            if not self._has_var_kw_arg and self._named_kw_args:
                # remove all unamed kw:
                copy = dict()
                for name in self._named_kw_args:
                    if name in kw:
                        copy[name] = kw[name]
                kw = copy
            # check named arg:
            for k, v in request.match_info.items():
                if k in kw:
                    logging.warning(
                        'Duplicate arg name in named arg and kw args: %s' % k)
                kw[k] = v
        if self._has_request_arg:
            kw['request'] = request
        # check required kw:
        if self._required_kw_args:
            for name in self._required_kw_args:
                if not name in kw:
                    return web.HTTPBadRequest('Missing argument: %s' % name)
        try:
            logging.info('call with args: %s' % str(kw))
            r = await self._fun(**kw)
            return r
        except APIError as e:
            return dict(error=e.error, data=e.data, message=e.message)


def add_route(app, fun):
    method = getattr(fun, '__method__', None)
    path = getattr(fun, '__path__', None)
    if method is None or path is None:
        raise ValueError('@get or @post not defined in %s' % fun.__name__)
    if not asyncio.iscoroutinefunction(fun) and not inspect.isgeneratorfunction(fun):
        fun = asyncio.coroutine(fun)
    logging.info('add route %s %s => %s' % (method, path, fun.__name__))
    app.router.add_route(method, path, RequestHandler(fun))


def add_routes(app, module_name):
    mod = __import__(module_name)
    for attr in dir(mod):
        if attr.startswith('_'):
            continue
        fun = getattr(mod, attr)
        if callable(fun):
            methed = getattr(fun, '__method__', None)
            path = getattr(fun, '__path__', None)
            if methed and path:
                add_route(app, fun)


def add_static(app):
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'static')
    app.router.add_static('/static/', path)
    logging.info('add static %s => %s' % ('/static/', path))


# def add_routes(app, module_name):
    # n = module_name.rfind('.')
    # if n == (-1):
    # mod = __import__(module_name, globals(), locals())
    # else:
    # name = module_name[n+1:]
    # mod = getattr(__import__(module_name[:n], globals(), locals(), [name]), name)
    # for attr in dir(mod):
    # if attr.startswith('_'):
    # continue
    # fn = getattr(mod, attr)
    # if callable(fn):
    # method = getattr(fn, '__method__', None)
    # path = getattr(fn, '__route__', None)
    # if method and path:
    # add_route(app, fn)
# # 添加一个模块的所有路由
# def add_routes(app, module_name):
    # try:
    # mod = __import__(module_name, fromlist=['get_submodule'])
    # except ImportError as e:
    # raise e
    # # 遍历mod的方法和属性,主要是找处理方法
    # # 由于我们定义的处理方法，被@get或@post修饰过，所以方法里会有'__method__'和'__route__'属性
    # for attr in dir(mod):
    # # 如果是以'_'开头的，一律pass，我们定义的处理方法不是以'_'开头的
    # if attr.startswith('_'):
    # continue
    # # 获取到非'_'开头的属性或方法
    # func = getattr(mod, attr)
    # # 获取有__method___和__route__属性的方法
    # if callable(func) and hasattr(func, '__method__') and hasattr(func, '__route__'):
    # args = ', '.join(inspect.signature(func).parameters.keys())
    # logging.info('add route %s %s => %s(%s)' % (func.__method__, func.__route__, func.__name__, args))
    # app.router.add_route(func.__method__, func.__route__, RequestHandler(func))
    # app.router.add_route(func.__method__, func.__route__, RequestHandler(func))
