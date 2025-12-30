import cachebox

# 测试 VTTLCache 创建
cache = cachebox.VTTLCache(maxsize=100, ttl=300)
print("VTTLCache created successfully")

# 查看所有方法
print("Available methods:", [m for m in dir(cachebox.VTTLCache) if not m.startswith('_')])

# 测试设置值
cache['key1'] = 'value1'
print('Set key1 successfully')

# 测试获取值
print('Get key1:', cache.get('key1'))

# 尝试设置带 TTL 的值
# 查看是否有 set 方法带 ttl 参数
print('Set method signature:', cachebox.VTTLCache.set)