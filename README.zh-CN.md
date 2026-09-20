# AirOps Desktop

<p align="center">
  <strong>轻量 · 离线优先 · 便携部署</strong>
</p>

<p align="center">
  <a href="./README.md">English</a> |
  <a href="./README.zh-CN.md">简体中文</a>
</p>

AirOps Desktop 是一个面向 **内网、隔离网、受限网络、无公网环境与 Air-Gapped 场景** 的轻量级 Windows 桌面网络运维工具。

它强调本地运行、低依赖、可复制部署，不要求运行时连接云服务、Web 服务端、Docker 或互联网。

> 当前状态：早期公开版 `v0.1.0`

## 为什么做 AirOps Desktop

很多生产网、专网、政企内网、实验环境和安全敏感网络无法直接使用 SaaS、云端 Agent 或在线运维平台。

这些环境通常有几个共同特点：

- 无法访问公网，或者严格限制公网访问；
- 网络与办公网、互联网存在逻辑或物理隔离；
- 设备型号多、协议旧、现场差异大；
- 需要通过 SSH / Telnet 批量登录设备执行巡检或配置采集；
- 不适合额外部署大型 Web 平台、数据库集群或容器环境；
- 运维数据、设备地址和账号信息必须保留在本地。

AirOps Desktop 希望解决的就是这一类场景：

> **把常用网络设备运维能力做成一个轻量、本地、可复制、无需云依赖的桌面工具。**

它不试图替代 NetBox、rConfig、Oxidized 等完整 NCM / DCIM 平台，而是更强调：

**开箱即用、离线运行、桌面交互、便携部署和现场适配。**

## 当前能力

- 本地设备资产管理
- SSH / Telnet 设备连接
- 自定义 SSH、Telnet、FTP 端口
- 设备模板与命令模板
- 并发连通性检测
- 批量设备并发执行
- 长时间、大体量 CLI 回显采集
- 特权模式 / Enable 支持
- FTP 文件下载
- 每日定时任务
- 执行历史记录
- Markdown 设备列表导入 / 导出
- 本地 SQLite 数据存储
- Portable Windows EXE
- 运行日志和设备执行结果本地保存

## 当前内置公共模板

公开仓库只提供通用或公开厂商模板：

- `Generic SSH`
- `Generic Telnet`
- `Huawei VRP`

真实生产环境中的设备类型、账号、地址、内部命令模板和配置数据不会进入公开仓库。

## 便携运行模式

AirOps Desktop 采用本地便携数据目录：

~~~text
AirOps-Desktop/
├─ AirOps-Desktop.exe
├─ data/
│  └─ airops_desktop.db
├─ logs/
└─ results/
~~~

复制整个目录即可迁移应用与本地数据，不依赖安装程序或服务端。

## 适合的使用场景

- 无公网访问的运维电脑
- 网络隔离环境
- 专网 / 内网设备巡检
- 小规模到中等规模交换机、路由器或网络设备批量运维
- 老旧设备 SSH / Telnet 混合环境
- 临时现场、实验室、测试环境
- 不希望部署完整 Web 运维平台的轻量场景

## 不适合的场景

AirOps Desktop 当前不是：

- 企业级 CMDB / DCIM 平台
- 多租户 SaaS 运维平台
- 大规模分布式自动化调度平台
- 零信任凭据管理系统
- 完整网络配置合规平台

如果设备规模、协作人数和自动化复杂度持续增长，NetBox、Oxidized、Nornir、rConfig 等成熟项目可能更合适。

## 安全说明

AirOps Desktop 的设计目标之一是减少对外部服务的依赖，但：

> **离线不等于天然安全。**

当前 `v0.1.0` 已知限制：

- 设备密码暂时以明文形式保存在本地 SQLite；
- Telnet 协议本身不加密；
- SSH 当前默认接受未知 Host Key；
- 本地数据库和执行结果依赖主机操作系统权限进行保护。

因此：

- Telnet 仅建议用于受信任隔离网络中的遗留设备；
- `data/`、`logs/`、`results/` 不应提交到 Git；
- 不要在 Issues、PR、测试样例中上传真实设备账号、配置或生产网络信息。

后续计划加入 Windows DPAPI 凭据保护、可配置 SSH Host Key 校验等能力。

详见 [SECURITY.md](SECURITY.md)。

## 开发

环境要求：

- Windows
- Python 3.11
- Tkinter / ttk
- SQLite
- Paramiko
- PyInstaller

~~~powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e .
python -m airops_desktop
~~~

也可以直接运行：

~~~powershell
run.bat
~~~

构建 Portable EXE：

~~~powershell
build_onefile.bat
~~~

输出：

~~~text
release/AirOps-Desktop.exe
~~~

## 路线图

- [ ] Driver / Model 设备驱动抽象
- [ ] Windows DPAPI 凭据加密
- [ ] SSH Host Key 校验策略
- [ ] 配置版本历史与 Diff
- [ ] 结构化巡检结果
- [ ] 更多公开设备 Driver
- [ ] Windows Release 自动发布
- [ ] 更完善的日志与错误诊断

## 贡献

欢迎提交 Issue 和 Pull Request。

提交示例或测试数据时，请：

- 使用 RFC 5737 文档地址：
  - `192.0.2.0/24`
  - `198.51.100.0/24`
  - `203.0.113.0/24`
- 不要提交真实生产 IP；
- 不要提交真实账号密码；
- 不要提交客户或项目名称；
- 不要提交生产配置文件和真实设备日志。

提交前建议运行：

~~~powershell
python scripts/check_public_safety.py
python -m unittest discover -s tests -v
~~~

## License

MIT License
