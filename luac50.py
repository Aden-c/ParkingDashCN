"""Parking Dash 脚本（Lua 5.0 字节码）读取 / 反汇编：python luac50.py 脚本.lua

注意：引擎改过操作码编号（共 39 个，0–11 与官方 5.0 相同，CALL=29），
所以 12 以后的操作码只显示为 OPnn。常量表、函数结构解析是完整的。"""
import sys, struct
OPN=["MOVE","LOADK","LOADBOOL","LOADNIL","GETUPVAL","GETGLOBAL","GETTABLE","SETGLOBAL","SETUPVAL","SETTABLE","NEWTABLE","SELF","ADD","SUB","MUL","DIV","POW","UNM","NOT","CONCAT","JMP","EQ","LT","LE","TEST","CALL","TAILCALL","RETURN","FORLOOP","TFORLOOP","TFORPREP","SETLIST","SETLISTO","CLOSE","CLOSURE"]
class R:
    def __init__(s,d): s.d=d; s.p=0
    def b(s,n): v=s.d[s.p:s.p+n]; s.p+=n; return v
    def u8(s): return s.b(1)[0]
    def i32(s): return struct.unpack('<i',s.b(4))[0]
    def u32(s): return struct.unpack('<I',s.b(4))[0]
    def num(s): return struct.unpack('<d',s.b(8))[0]
    def st(s):
        n=s.u32()
        if n==0: return None
        return s.b(n)[:-1].decode('latin1')
def func(r):
    f={}
    f['src']=r.st(); f['line']=r.i32()
    f['nups'],f['np'],f['va'],f['ms']=r.u8(),r.u8(),r.u8(),r.u8()
    n=r.i32(); f['li']=[r.i32() for _ in range(n)]
    n=r.i32(); f['loc']=[(r.st(),r.i32(),r.i32()) for _ in range(n)]
    n=r.i32(); f['ups']=[r.st() for _ in range(n)]
    n=r.i32(); K=[]
    for _ in range(n):
        t=r.u8()
        if t==0: K.append(None)
        elif t==3: K.append(r.num())
        elif t==4: K.append(r.st())
        else: raise Exception('bad k %d at %d'%(t,r.p))
    f['k']=K
    n=r.i32(); f['p']=[func(r) for _ in range(n)]
    n=r.i32(); f['code']=[r.u32() for _ in range(n)]
    return f
def load(path):
    d=open(path,'rb').read(); r=R(d)
    assert r.b(4)==b'\x1bLua' and r.u8()==0x50
    r.b(17)
    f=func(r); assert r.p==len(d), (r.p,len(d))
    f['_hdr']=d[:22]   # 文件头原样保留，dump 时写回
    return f


# ---- 写回（load 的逆过程；修改常量 / 指令后用它生成新的字节码文件） ----
def _st(s):
    if s is None: return struct.pack('<I',0)
    b=s.encode('latin1')+b'\0'; return struct.pack('<I',len(b))+b
def _func(f):
    o=bytearray()
    o+=_st(f['src'])+struct.pack('<i',f['line'])+bytes([f['nups'],f['np'],f['va'],f['ms']])
    o+=struct.pack('<i',len(f['li']))+b''.join(struct.pack('<i',x) for x in f['li'])
    o+=struct.pack('<i',len(f['loc']))+b''.join(_st(n)+struct.pack('<ii',a,b) for n,a,b in f['loc'])
    o+=struct.pack('<i',len(f['ups']))+b''.join(_st(u) for u in f['ups'])
    o+=struct.pack('<i',len(f['k']))
    for k in f['k']:
        if k is None: o+=b'\0'
        elif isinstance(k,float): o+=b'\3'+struct.pack('<d',k)
        else: o+=b'\4'+_st(k)
    o+=struct.pack('<i',len(f['p']))+b''.join(_func(p) for p in f['p'])
    o+=struct.pack('<i',len(f['code']))+b''.join(struct.pack('<I',i) for i in f['code'])
    return bytes(o)
def dump(f):
    return f['_hdr']+_func(f)
def const_index(f, v):
    """常量 v 在函数 f 常量表里的下标，没有就追加到末尾"""
    for i,k in enumerate(f['k']):
        if type(k) is type(v) and k==v: return i
    f['k'].append(v); return len(f['k'])-1
def RK(f,x): return (repr(f['k'][x-250]) if x-250<len(f['k']) else 'k%d'%(x-250)) if x>=250 else 'r%d'%x
def fmt(v):
    if isinstance(v,float) and v==int(v): return str(int(v))
    return repr(v)
def dis(f, ind=''):
    print(ind+'function line %s params %d, %d consts, %d instr'%(f['line'],f['np'],len(f['k']),len(f['code'])))
    for pc,i in enumerate(f['code']):
        op=i&0x3f; C=(i>>6)&0x1ff; B=(i>>15)&0x1ff; A=i>>24; Bx=(i>>6)&0x3ffff; sBx=Bx-131071
        o=OPN[op] if op<12 else 'OP%d'%op
        if o in('LOADK','GETGLOBAL','SETGLOBAL'): a='%d %s'%(A,fmt(f['k'][Bx]))
        elif o in('GETTABLE','SELF'): a='%d r%d[%s]'%(A,B,RK(f,C))
        elif o=='SETTABLE': a='r%d[%s]=%s'%(A,RK(f,B),RK(f,C))
        elif o in('ADD','SUB','MUL','DIV','EQ','LT','LE'): a='%d %s %s'%(A,RK(f,B),RK(f,C))
        elif o in('JMP','FORLOOP','TFORPREP'): a='%d'%sBx
        else: a='%d %s %s'%(A,RK(f,B),RK(f,C))
        print(ind+'  %4d %-9s %s'%(pc,o,a))
    for p in f['p']: dis(p, ind+'    ')
if __name__=='__main__':
    dis(load(sys.argv[1]))
