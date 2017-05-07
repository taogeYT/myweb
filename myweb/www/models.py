import time, uuid
from orm import Model, IntegerField, StringField, BooleanField, FloatField, TextField

def next_id():
    return '%015d%s' % (int(time.time() * 1000), uuid.uuid4().hex) #uuid4 用于随机生成一个UUID 
    
class Test(Model):
    __table__='test'
    id = IntegerField(primary_key=True)
    name = StringField()
    password = StringField()
    created_at = FloatField(default=time.time)


class User(Model):
    __table__ = 'users'

    id = StringField(primary_key=True, default=next_id, field_type='varchar(50)')
    email = StringField(field_type='varchar(50)')
    passwd = StringField(field_type='varchar(50)')
    admin = BooleanField()
    name = StringField(field_type='varchar(50)')
    image = StringField(field_type='varchar(500)')
    created_at = FloatField(default=time.time)

class Blog(Model):
    __table__ = 'blogs'

    id = StringField(primary_key=True, default=next_id, field_type='varchar(50)')
    user_id = StringField(field_type='varchar(50)')
    user_name = StringField(field_type='varchar(50)')
    user_image = StringField(field_type='varchar(500)')
    name = StringField(field_type='varchar(50)')
    summary = StringField(field_type='varchar(200)')
    content = TextField()
    created_at = FloatField(default=time.time)

class Comment(Model):
    __table__ = 'comments'

    id = StringField(primary_key=True, default=next_id, field_type='varchar(50)')
    blog_id = StringField(field_type='varchar(50)')
    user_id = StringField(field_type='varchar(50)')
    user_name = StringField(field_type='varchar(50)')
    user_image = StringField(field_type='varchar(500)')
    content = TextField()
    created_at = FloatField(default=time.time)
