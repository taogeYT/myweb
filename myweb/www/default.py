class Dict(dict):
	def __getattr__(self,key):
		try:
			return self[key]
		except KeyError:
			raise AttributeError(r"'Dict' object has no attribute '%s'" % key)
def toDict(d):
	D = Dict()
	for i,j in d.items():
		D[i] = toDict(j) if isinstance(j,dict) else j
	return D


configs = dict(
	sql=dict(
		host='localhost',
		port=3306, 
		user='root', 
		password='password', 
		db='awesome'
		),
	cookie_key='yt'
)

cfg = toDict(configs)