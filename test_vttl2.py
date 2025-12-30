import cachebox

# 测试 VTTLCache 创建
cache = cachebox.VTTLCache(maxsize=100, ttl=300)

# 查看 insert 方法
help(cache.insert)