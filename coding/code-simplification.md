---
name: code-simplification
description: 在不改变行为的前提下重构代码以提升可读性。代码能跑但难读、难维护、难扩展时，或者审查中发现堆积起来的复杂性时，使用此技能。
---

# 概览

在行为完全一致的前提下降低代码的复杂性。衡量标准是理解速度而不是行数：新成员读简化后的版本，能否比读原版更快搞懂它在做什么。

## 何时使用

- 功能已完成、测试已通过，但实现方式笨重
- 代码审查提出了可读性或复杂性问题
- 出现三层以上嵌套、超长函数、含义模糊的命名
- 重构赶工期写下的代码
- 合并之后出现了重复或不一致的逻辑

## 何时不使用

- 代码已经清晰，没有可改的地方
- 你还没搞懂这段代码在做什么
- 代码在性能敏感路径上，简化后会明显变慢
- 该模块即将重写，简化的成果会被一起扔掉

## 原则

### 1. 行为完全不变

只改表达方式，不改功能。输入输出、副作用、错误处理、边缘情况必须全部保持一致。不确定某项改动是否保持行为，就不要做。

每次改动前逐条确认：

- 每个输入产生的输出都相同吗
- 错误处理路径相同吗
- 副作用及其发生顺序相同吗
- 现有测试不做任何修改就能通过吗

### 2. 向项目规范靠拢

简化是让代码更贴近代码库里的既有写法，不是套用个人偏好。动手前先读 CLAUDE.md 或项目规范，再看相邻代码怎么处理同类问题，然后在导入顺序、函数声明方式、命名、错误处理、类型标注深度上与之对齐。破坏一致性的改动只是变动，不是简化。

### 3. 清晰优先于精巧

代码需要停下来解析才能读懂，就写成显式的形式。

```typescript
// 不清晰：连写的嵌套三元
const label = isNew ? 'New' : isUpdated ? 'Updated' : isArchived ? 'Archived' : 'Active';

// 清晰：逐条判断
function getStatusLabel(item: Item): string {
  if (item.isNew) return 'New';
  if (item.isUpdated) return 'Updated';
  if (item.isArchived) return 'Archived';
  return 'Active';
}
```

```typescript
// 不清晰：reduce 里塞进了展开和计数两件事
const result = items.reduce((acc, item) => ({
  ...acc,
  [item.id]: { ...acc[item.id], count: (acc[item.id]?.count ?? 0) + 1 }
}), {});

// 清晰：中间结果有名字
const countById = new Map<string, number>();
for (const item of items) {
  countById.set(item.id, (countById.get(item.id) ?? 0) + 1);
}
```

### 4. 不要简化过头

- 内联掉一个给概念命名的辅助函数，调用处会更难读
- 把两个简单函数并成一个复杂函数，不是简化
- 有些抽象是为可测试性或扩展点而存在的，删掉会丢掉这部分能力
- 行数减少但理解成本上升，是负收益

### 5. 只动本次任务范围内的代码

默认只简化刚改过的代码。没有明确要求就不要顺手重构无关部分，这会让 diff 变脏，也会在你本来不打算碰的地方引入回归。

## 流程

### 一、先弄清它为什么存在

切斯特顿围栏：不明白路上的围栏为什么在那儿，就先别拆，查清原因，再判断这个原因今天是否还成立。

动手前回答：

- 这段代码负责什么
- 谁调用它，它调用谁
- 边缘情况和错误路径有哪些
- 有没有测试定义了它的预期行为
- 为什么写成这样，是性能、平台限制还是历史遗留
- git blame 显示它当初是在什么背景下写的

答不上来就继续读上下文，还不到动手的时候。

### 二、找出可简化的点

结构复杂性：

| 模式 | 信号 | 简化方案 |
|---|---|---|
| 深度嵌套（3 层以上） | 控制流难以追踪 | 把条件提取为卫语句或辅助函数 |
| 冗长函数（50 行以上） | 一个函数干了好几件事 | 拆成职责单一、命名有描述性的函数 |
| 嵌套三元 | 读的时候要同时记住多个分支 | 换成 if/else 链、switch 或查找表 |
| 布尔参数标志 | `doThing(true, false, true)` | 换成选项对象或独立函数 |
| 重复的条件判断 | 多处出现相同的 if 检查 | 提取为命名良好的断言函数 |

命名与可读性：

| 模式 | 信号 | 简化方案 |
|---|---|---|
| 泛泛的命名 | `data`、`result`、`temp`、`val` | 改成说明内容的名字，如 `userProfile`、`validationErrors` |
| 缩写命名 | `usr`、`cfg`、`btn`、`evt` | 用完整单词，除非缩写是通用的，如 `id`、`url`、`api` |
| 误导性命名 | 叫 `get` 的函数却修改了状态 | 改成反映真实行为的名字 |
| 说明「做什么」的注释 | `count++` 上面写着「增加计数器」 | 删掉，代码本身已经说清楚了 |
| 说明「为什么」的注释 | 「API 在高负载下不稳定，所以重试」 | 保留，这类信息代码表达不出来 |

冗余：

| 模式 | 信号 | 简化方案 |
|---|---|---|
| 重复逻辑 | 相同的 5 行以上代码出现在多处 | 提取为共享函数 |
| 死代码 | 无法触达的分支、未使用的变量、注释掉的代码块 | 确认无用后删除 |
| 无价值的包装层 | 包装函数没有增加任何东西 | 内联，直接调用底层函数 |
| 投机性抽象 | 为「以后可能用到」保留的扩展点，当前没有调用者 | 删掉，需要时再加回来 |
| 过度设计的模式 | 生产工厂的工厂、只有一个实现的策略模式 | 换成直接调用 |
| 冗余类型断言 | 断言一个已经能推断出来的类型 | 删掉断言 |

### 三、逐项修改，改一项测一次

一次只做一项简化：改完跑测试，通过就提交或继续下一项，不通过就还原并重新考虑。不要把多项未经测试的简化打包在一起，出问题时你需要立刻知道是哪一项造成的。

重构和功能开发、Bug 修复分开提交。一个既重构又加功能的 PR 应该拆成两个。

改动超过 500 行时，改用自动化工具完成，如 codemod、sed 脚本或 AST 转换。这个规模的手工编辑容易出错，也很难审查。

### 四、回头看整体

全部改完后对比前后两个版本：简化后是否真的更好懂，是否引入了代码库里没有的新写法，diff 是否干净好审，同事会不会批准这个改动。如果简化后的版本反而更难读或更难审，还原它。不是每次尝试都会成功。

## 语言示例

### TypeScript / JavaScript

```typescript
// 去掉多余的 async 包装
// 改前
async function getUser(id: string): Promise<User> {
  return await userService.findById(id);
}
// 改后
function getUser(id: string): Promise<User> {
  return userService.findById(id);
}
// 注意：如果 return await 位于 try 块内，去掉 await 会让 catch 不再捕获这个 Promise 的拒绝，
// 这是行为改变，不能改。
```

```typescript
// 合并啰嗦的条件赋值
// 改前
let displayName: string;
if (user.nickname) {
  displayName = user.nickname;
} else {
  displayName = user.fullName;
}
// 改后
const displayName = user.nickname || user.fullName;
// 注意：只有当原判断确实是真假判断时才能这样改。`??` 只在 null 和 undefined 时回退，
// 空字符串、0、false 的处理结果与 `||` 不同。
```

### Python

```python
# 用推导式替换手工构建字典
# 改前
result = {}
for item in items:
    result[item.id] = item.name
# 改后
result = {item.id: item.name for item in items}

# 用卫语句拆掉嵌套条件
# 改前
def process(data):
    if data is not None:
        if data.is_valid():
            if data.has_permission():
                return do_work(data)
            else:
                raise PermissionError("No permission")
        else:
            raise ValueError("Invalid data")
    else:
        raise TypeError("Data is None")
# 改后
def process(data):
    if data is None:
        raise TypeError("Data is None")
    if not data.is_valid():
        raise ValueError("Invalid data")
    if not data.has_permission():
        raise PermissionError("No permission")
    return do_work(data)
```

### React / JSX

```tsx
// 合并只有取值不同的分支
// 改前
function UserBadge({ user }: Props) {
  if (user.isAdmin) {
    return <Badge variant="admin">Admin</Badge>;
  } else {
    return <Badge variant="default">User</Badge>;
  }
}
// 改后
function UserBadge({ user }: Props) {
  const variant = user.isAdmin ? 'admin' : 'default';
  const label = user.isAdmin ? 'Admin' : 'User';
  return <Badge variant={variant}>{label}</Badge>;
}
```

跨多层组件的属性钻取属于结构取舍，改成 Context 或组合会影响组件边界，超出行为不变的范围。标记出来交给人决定，不要自动重构。

## 完成前的检查

- [ ] 现有测试不做任何修改即可通过
- [ ] 构建通过，没有新增警告
- [ ] Linter 和格式化检查通过
- [ ] 每项简化都是一个可单独审查的小改动
- [ ] diff 里没有混进无关改动
- [ ] 结果符合项目规范，参照 CLAUDE.md 或等效文件
- [ ] 没有任何错误处理被删掉或削弱
- [ ] 没有留下死代码，包括未使用的导入和无法触达的分支

有一条不满足，就还原对应的改动。其中需要改测试才能通过这一条最值得警惕，它几乎总是意味着行为被改了。
