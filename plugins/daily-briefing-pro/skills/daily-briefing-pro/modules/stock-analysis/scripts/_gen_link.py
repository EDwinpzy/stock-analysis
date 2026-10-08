import urllib.parse
p = r'./outputs\个股分析\高争民爆深度研究报告.html'
p = p.replace('\\', '/')
parts = p.split('/')
first = parts[0]
rest = '/'.join(urllib.parse.quote(seg) for seg in parts[1:])
print('file:///' + first + '/' + rest)
