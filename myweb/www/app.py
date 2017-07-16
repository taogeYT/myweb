#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
awesome web app

just to learn python by this project, and can understand python usually modules
"""

__version__ = '1.0.0'
__all__ = ['init', 'main']
__author__ = 'liyatao'

import logging
import asyncio
import os
import json
import time
from aiohttp import web
from datetime import datetime
from coroweb import add_routes, add_static
import orm
log_format = '[%(asctime)s %(levelname)s %(module)s]: %(message)s'
logging.basicConfig(format=log_format, level=logging.INFO)  # INFO WARNING ERROR
from handlers import cookie2user, COOKIE_NAME
from jinja2 import FileSystemLoader, Environment


# 这个函数功能是初始化jinja2模板，配置jinja2的环境
def init_jinja2(app, **kw):
    logging.info('init jinja2...')
    # 设置解析模板需要用到的环境变量
    options = dict(
        # 自动转义xml/html的特殊字符（这是别的同学的注释，我不知道特殊字符具体指的是什么）
        autoescape=kw.get('autoescape', True),
        # 设置代码块起始字符串，还有下面那句是结束字符串
        block_start_string=kw.get('block_start_string', '{%'),
        # 意思就是{%和%}中间是python代码，而不是html
        block_end_string=kw.get('block_end_string', '%}'),
        variable_start_string=kw.get(
            'variable_start_string', '{{'),  # 这两句分别设置了变量的起始和结束字符串
        # 就是说{{和}}中间是变量，看过templates目录下的test.html文件后就很好理解了
        variable_end_string=kw.get('variable_end_string', '}}'),
        # 当模板文件被修改后，下次请求加载该模板文件的时候会自动重新加载修改后的模板文件
        auto_reload=kw.get('auto_reload', True)
    )
    # 从**kw中获取模板路径，如果没有传入这个参数则默认为None
    path = kw.get('path', None)
    # 如果path为None，则将当前文件所在目录下的templates目录设置为模板文件的目录
    if path is None:
        # 下面这句代码其实是三个步骤，先取当前文件也就是app.py的绝对路径，然后取这个绝对路径的目录部分，最后在这个目录后面加上templates子目录
        path = os.path.join(
            os.path.dirname(os.path.abspath(__file__)), 'templates'
        )
    logging.info('set jinja2 template path: %s' % path)
    # loader=FileSystemLoader(path)指的是到哪个目录下加载模板文件，**options就是前面的options，用法和**kw类似
    env = Environment(loader=FileSystemLoader(path), **options)
    # 过滤器作用是对html文档中的要加载的变量做进一步处理后在显示，而不是直接显示变量的值，该时间过滤器作用是把时间戳转换成多久前显示
    filters = kw.get('filters', None)
    if filters is not None:
        for name, f in filters.items():
            env.filters[name] = f
    # 前面已经把jinja2的环境配置都赋值给env了，这里再把env存入app的属性中方便调用，这样app就知道要到哪儿去找模板，怎么解析模板。
    app.__templating__ = env


# middle函数
async def logger_factory(app, handler):
    async def logger(request):
        print(request.query_string)
        logging.info('Server receviced a Request: %s %s' %
                     (request.method, request.path))
        return (await handler(request))
    return logger


async def data_factory(app, handler):
    async def parse_data(request):
        if request.method == 'POST':
            if request.content_type.startswith('application/json'):
                request.__data__ = await request.json()
                logging.info('request json: %s' % str(request.__data__))
            elif request.content_type.startswith('application/x-www-form-urlencoded'):
                request.__data__ = await request.post()
                logging.info('request form: %s' % str(request.__data__))
        return (await handler(request))
    return parse_data


async def auth_factory(app, handler):
    async def auth(request):
        logging.info('start user authentication: %s %s' %
                     (request.method, request.path))
        request.__user__ = None
        cookie_str = request.cookies.get(COOKIE_NAME)
        if cookie_str:
            print(cookie_str)
            user = await cookie2user(cookie_str)
            print(user)
            if user:
                logging.info('user %s authentication pass' % user.email)
                request.__user__ = user
        if request.path.startswith('/manage/') and (request.__user__ is None or not request.__user__.admin):
            logging.warning('need administrator account to sign in')
            return web.HTTPFound('/signin')
        return (await handler(request))
    return auth


async def response_factory(app, handler):
    async def response(request):
        logging.info('Server start Response by handler')
        r = await handler(request)
        if isinstance(r, web.StreamResponse):
            return r
        if isinstance(r, bytes):
            resp = web.Response(body=r)
            resp.content_type = 'application/octet-stream'
            return resp
        if isinstance(r, str):
            if r.startswith('redirect:'):
                return web.HTTPFound(r[9:])
            resp = web.Response(body=r.encode('utf-8'))
            resp.content_type = 'text/html;charset=utf-8'
            return resp
        if isinstance(r, dict):
            template = r.get('__template__')
            if template is None:
                resp = web.Response(body=json.dumps(
                    r, ensure_ascii=False, default=lambda o: o.__dict__).encode('utf-8'))
                resp.content_type = 'application/json;charset=utf-8'
                return resp
            else:
                # 通过auth_factory中返回的request.__user__值来确定用户是否登录成功状态
                r['__user__'] = request.__user__
                resp = web.Response(body=app.__templating__.get_template(
                    template).render(**r).encode('utf-8'))
                resp.content_type = 'text/html;charset=utf-8'
                return resp
        if isinstance(r, int) and r >= 100 and r < 600:
            return web.Response(r)
        if isinstance(r, tuple) and len(r) == 2:
            t, m = r
            if isinstance(t, int) and t >= 100 and t < 600:
                return web.Response(t, str(m))
        # default:
        logging.info('Server end Response by handler')
        resp = web.Response(body=str(r).encode('utf-8'))
        resp.content_type = 'text/plain;charset=utf-8'
        return resp
    return response


# 这个时间过滤器的作用其实可以猜出来，返回日志创建的大概时间，用于显示在日志标题下面，这会儿暂时用不到
def datetime_filter(t):
    delta = int(time.time() - t)
    if delta < 60:
        return u'1分钟前'
    if delta < 3600:
        return u'%s分钟前' % (delta // 60)
    if delta < 86400:
        return u'%s小时前' % (delta // 3600)
    if delta < 604800:
        return u'%s天前' % (delta // 86400)
    dt = datetime.fromtimestamp(t)
    return u'%s年%s月%s日' % (dt.year, dt.month, dt.day)


async def init(loop):
    await orm.create_pool(loop=loop, host='localhost', port=3306, user='root', password='password', db='awesome')
    app = web.Application(loop=loop, middlewares=[
                          logger_factory, data_factory, auth_factory, response_factory])
    # 初始化jinja2模板，并传入时间过滤器
    init_jinja2(app, filters=dict(datetime=datetime_filter))
    # 添加操作路由
    add_routes(app, 'handlers')
    add_static(app)
    srv = await loop.create_server(app.make_handler(), '0.0.0.0', 9090)
    logging.info('Server started at http://localhost:9000')
    print('Server started at http://localhost:9000')
    return srv


def main():
    loop = asyncio.get_event_loop()
    loop.run_until_complete(init(loop))
    loop.run_forever()


if __name__ == '__main__':
    main()
