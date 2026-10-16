# 备份与恢复

spec §8：备份 = 卷 + 数据库 dump。代码在 git 里，**不在 git 里的三样**要备：

| 内容 | 位置 | 备份产物 |
|---|---|---|
| 数据库（衣物、记录、穿着历史、向量索引、设置） | postgres 卷 `wardrowbe_postgres_data` | `db.dump`（`pg_dump -Fc`） |
| 图片（原图、`_src` / `_orig` 副本、mask、三档缩略、穿搭照） | 卷 `wardrowbe_wardrobe_data`（容器内 `/data/wardrobe`） | `wardrobe_data.tar.gz` |
| 词表（设置页增改会写回） | `backend/app/data/garment_vocabulary.json`（bind-mount） | `garment_vocabulary.json` |

另附 `commit.txt`（当时的代码版本）和 `alembic.txt`（当时的迁移版本），恢复时对版本用。

`.env` 不进备份（里面是本地服务 key），自己另存一份。redis 只是任务队列，不用备。

## 备份

服务开着的时候跑（要 postgres 在线）：

```bash
scripts/backup.sh                     # 默认放 ~/wardrobe-backups/<时间戳>/
scripts/backup.sh /mnt/d/backups/wardrobe   # 放到 Windows D 盘，WSL 坏了也还在
```

脚本最后会检查 dump 非空、tar 能列出，不过关就报错退出。

建议：录入一批或改完词表后跑一次；至少放一份在 WSL 之外（D 盘或网盘）。
旧备份自己删，脚本不轮转。

## 恢复

以下会**覆盖**现有数据。恢复前先对现状再跑一次 `scripts/backup.sh` 留底。

```bash
B=~/wardrobe-backups/<时间戳>      # 要恢复的那一份

# 0. 代码切到备份时的版本或更新（不能比备份旧，否则库结构对不上）
cat $B/commit.txt $B/alembic.txt

# 1. 停应用，只留 postgres
docker compose stop frontend backend worker image-worker

# 2. 数据库：先清后灌
docker compose exec -T postgres sh -c 'pg_restore -U "$POSTGRES_USER" -d "$POSTGRES_DB" --clean --if-exists --no-owner' < $B/db.dump

# 3. 图片卷：清空后解包
docker run --rm -v wardrowbe_wardrobe_data:/data -v $B:/backup alpine \
  sh -c 'rm -rf /data/* /data/.[!.]* 2>/dev/null; tar xzf /backup/wardrobe_data.tar.gz -C /data'

# 4. 词表
cp $B/garment_vocabulary.json backend/app/data/

# 5. 起服务，把库升到当前代码的迁移版本（备份更旧时才有事做）
docker compose up -d
docker compose exec backend alembic upgrade head
```

恢复后打开网页确认衣物图都在。向量索引随数据库一起恢复；若之后换了 embedding 模型，后台会自动重算。

**换机器**：新机器上 clone 代码、配好 `.env`、`docker compose up -d` 让卷建出来，再按上面 1–5 走。卷名前缀是 compose 项目名（默认目录名 `wardrowbe`），目录名不同时把 `wardrowbe_wardrobe_data` 换成实际名（`docker volume ls` 看）。
