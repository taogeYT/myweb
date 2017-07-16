import asyncio
import logging
import aiomysql
import sys
# log_format = '%(levelname)s %(filename)s %(message)s'
# logging.basicConfig(format=log_format,level=logging.INFO)
# logging.basicConfig(level=logging.INFO)


@asyncio.coroutine
def create_pool(loop, **kw):
    logging.info('create database connection pool...')
    global __pool
    __pool = yield from aiomysql.create_pool(
        host=kw.get('host', 'localhost'),
        port=kw.get('port', 3306), user=kw['user'],
        password=kw['password'],
        db=kw['db'],
        charset=kw.get('charset', 'utf8'),
        autocommit=kw.get('autocommit', True),
        maxsize=kw.get('maxsize', 16000),
        minsize=kw.get('minsize', 1),
        loop=loop)


@asyncio.coroutine
def select(sql, args=None, size=None):
    # log(sql,args)
    global __pool
    with (yield from __pool) as conn:
        cur = yield from conn.cursor(aiomysql.DictCursor)
        yield from cur.execute(sql.replace('?', '%s'), args or ())
        if size:
            rs = yield from cur.fetchmany(size)
        else:
            rs = yield from cur.fetchall()
        yield from cur.close()
        return rs


@asyncio.coroutine
def execute(sql, args, autocommit=True):
    # log(sql)
    global __pool
    with (yield from __pool) as conn:
        if not autocommit:
            yield from conn.begin()
        try:
            cur = yield from conn.cursor(aiomysql.DictCursor)
            yield from cur.execute(sql.replace('?', '%s'), args)
            affected = cur.rowcount
            yield from cur.close()
            if not autocommit:
                yield from conn.commit()
        except BaseException as e:
            if not autocommit:
                yield from conn.rollback()
            raise
        return affected

# 把序列中元素通过','相连一个字符串


def create_args_string(num):
    L = []
    for n in range(num):
        L.append('?')
    return ','.join(L)


class Field(object):

    def __init__(self, name, column_type, primary_key, default):
        self.name = name
        self.column_type = column_type
        self.primary_key = primary_key
        self.default = default

    def __str__(self):
        return '<%s %s:%s>' % (self.__class__.__name__, self.column_type, self.name)


class StringField(Field):

    def __init__(self, name=None, primary_key=False, default=None, field_type='varchar(100)'):
        super().__init__(name, field_type, primary_key, default)


class BooleanField(Field):

    def __init__(self, name=None, default=False):
        super().__init__(name, 'boolean', False, default)


class IntegerField(Field):

    def __init__(self, name=None, primary_key=False, default=0):
        super().__init__(name, 'bigint', primary_key, default)


class FloatField(Field):

    def __init__(self, name=None, primary_key=False, default=0.0):
        super().__init__(name, 'real', primary_key, default)


class TextField(Field):

    def __init__(self, name=None, default=None):
        super().__init__(name, 'text', False, default)


class ModelMetaclass(type):

    def __new__(cls, name, bases, attrs):
        if name == 'Model':
            return type.__new__(cls, name, bases, attrs)
        tableName = attrs.get('__table__', None) or name
        logging.info('creating model %s (table name:%s)' % (name, tableName))
        # 获取所有的Field和主键名:
        mappings = {}
        fields = []
        primaryKey = None
        for k, v in attrs.items():
            if isinstance(v, Field):
                logging.info('found maping: %s => %s' % (k, v))
                mappings[k] = v
                if v.primary_key:
                    logging.info('found primary key => %s' % k)
                    # 防止主键重复
                    if primaryKey:
                        raise RuntimeError(
                            'Duplicate primary key for field:%s' % k)
                    primaryKey = k
                else:
                    fields.append(k)
        if not primaryKey:
            raise RuntimeError('primray key no found.')
        for k in mappings.keys():
            attrs.pop(k)
        escaped_fields = list(map(lambda f: '`%s`' % f, fields))
        attrs['__mappings__'] = mappings
        attrs['__fields__'] = fields
        attrs['__table__'] = tableName
        attrs['__primary_key__'] = primaryKey
        # attrs['__select__']='select `%s` %s from `%s`'%(primaryKey,','.join(escaped_fields),tableName)
        attrs['__select__'] = 'select * from `%s`' % (tableName)
        attrs['__insert__'] = 'insert into `%s` (%s,`%s`) values (%s)' % (
            tableName, ','.join(escaped_fields), primaryKey, create_args_string(len(fields) + 1))
        attrs['__delete__'] = 'delete from `%s` where `%s`=?' % (
            tableName, primaryKey)
        attrs['__update__'] = 'update `%s` set %s where `%s`=?' % (tableName, ','.join(
            map(lambda f: '`%s`=?' % (mappings.get(f).name or f), fields)), primaryKey)
        return type.__new__(cls, name, bases, attrs)


class Model(dict, metaclass=ModelMetaclass):

    def __init__(self, **kw):
        super().__init__(**kw)

    def __getattr__(self, key):
        try:
            return self[key]
        except KeyError:
            raise AttributeError(r"'Model' object has no attribute '%s'" % key)

    def __setattr__(self, key, value):
        self[key] = value

    def getValueOrDefault(self, key):
        value = getattr(self, key, None)
        if value is None:
            field = self.__mappings__[key]
            if field.default is not None:
                value = field.default() if callable(field.default) else field.default
                logging.debug('using default value for %s : %s' % (key, value))
                setattr(self, key, value)  # 将该字段的默认值写进实例对象
        return value

    def getvalue(self, key):
        return self[key]

    @classmethod
    @asyncio.coroutine
    def find_all(cls, where=None, args=None, order_by=None, limit=None):
        sql = [cls.__select__]
        if where:
            sql.append('where %s' % where)
        if order_by:
            sql.append('order by %s' % order_by)
        if args:
            if not isinstance(args, list):
                args = [args]
        else:
            args = []
        if limit:
            if isinstance(limit, int):
                sql.append('limit ?')
                args.append(limit)  # 列表里增加一个元素
            elif isinstance(limit, tuple) and len(limit) == 2:
                sql.append('limit ?,?')
                args.extend(limit)  # 列表里增加一个列表
            else:
                raise ValueError('Invalid limit value:%s' % str(limit))
        rs = yield from select(' '.join(sql), args)
        print('all:', rs)
        return [cls(**r) for r in rs]  # 将字典重新封装成当前类的对象，方便返回值使用类一些属性，比如user.id

    @classmethod
    async def find_number(cls, field='*', where=None, args=None):
        sql = ['select count(%s) num from %s' % (field, cls.__table__)]
        if where:
            sql.append('where %s' % where)
        rs = await select(' '.join(sql), args, 1)
        if len(rs) == 0:
            return None
        return rs[0]['num']

    @classmethod
    @asyncio.coroutine
    def find(cls, pk):
        'find objects by primary key'
        rs = yield from select('%s where `%s`=?' % (cls.__select__, cls.__primary_key__), pk)
        print('one:', rs)
        if len(rs) == 0:
            return None
        return cls(**rs[0])

    @asyncio.coroutine
    def save(self):
        args = list(map(self.getValueOrDefault, self.__fields__))
        args.append(self.getValueOrDefault(self.__primary_key__))
        rows = yield from execute(self.__insert__, args)
        if rows != 1:
            logging.warn('failed to insert record: affected rows: %s' % rows)

    @asyncio.coroutine
    def update(self):
        args = list(map(self.getValueOrDefault, self.__fields__))
        args.append(self.getValueOrDefault(self.__primary_key__))
        rows = yield from execute(self.__update__, args)
        if rows != 1:
            logging.warn('failed to update record: affected rows: %s' % rows)


if __name__ == '__main__':
    # 创建实例
    @asyncio.coroutine
    def test():
        class Test(Model):
            __table__ = 'test'
            id = IntegerField(primary_key=True)
            name = StringField()
            password = StringField()
        yield from create_pool(loop=loop, host='localhost', port=3306, user='root', password='password', db='awesome')
        t = Test(id=2, name='lyt', password='123123')
        rs = yield from Test.find(2)
        if rs:
            rs1 = yield from t.update()
        else:
            rs1 = yield from t.save()
        print(rs1)
        rs2 = yield from Test.find_all()
        print(rs2)
        # 引用全局变量__pool(连接地址池)
        global __pool
        # 关闭所有数据库连接
        __pool.close()
        yield from __pool.wait_closed()

    loop = asyncio.get_event_loop()
    loop.run_until_complete(test())
    print('end')
    loop.close()
