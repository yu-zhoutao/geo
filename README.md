# Geo Agent

面向东北黑土区多源遥感与地学分析的智能体原型。项目将 OpenCode 运行时、地理空间 Python 工具和 Vue 前端组合为可复现的分析工作流。

## 功能

- NE01：土地覆盖变化与 NDVI/EVI 植被响应分析
- NE02：气候—植被时空异常与变率分析
- NE03：地形—气候—植被综合生态分区
- 本地 OpenCode 模型运行时与地理空间 MCP 工具
- GeoTIFF、CSV、PNG、PDF 和 SVG 等分析结果输出

## 环境准备

1. 安装 Python 3.12、`uv`、Node.js 和 npm。
2. 安装 Python 依赖：

   ```bash
   uv sync
   ```

3. 安装前端依赖：

   ```bash
   cd frontend
   npm install
   cd ..
   ```

4. 复制 `.env.example` 为 `.env`，并填写自己的模型 API 密钥。`.env` 不应提交到 Git。
5. 设置数据目录：

   ```bash
   export GEO_AGENT_DATA_ROOT=/path/to/your/dataset
   ```

数据目录应包含 `CDL/`、`MODIS/`、`ERA5_Land/`、`DEM/` 和 `Shapefiles/` 等子目录。原始数据不随代码仓库发布。

## 运行三个分析任务

```bash
python scripts/run_ne01_land_cover_vegetation_change.py --data-root "$GEO_AGENT_DATA_ROOT"
python scripts/run_ne02_climate_vegetation_stress.py --data-root "$GEO_AGENT_DATA_ROOT"
python scripts/run_ne03_terrain_climate_ecological_zones.py --data-root "$GEO_AGENT_DATA_ROOT"
```

结果默认写入 `outputs/`；该目录被 Git 忽略，适合在本地生成，不纳入公开仓库。

## 启动应用

后端：

```bash
uv run uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

前端：

```bash
cd frontend
npm run dev -- --host ::
```

浏览器访问 <http://localhost:5173/>。

## 研究与复现边界

项目输出用于描述性空间分析、变化检测、时空统计和探索性生态分区，不自动构成因果归因、产量预测或地面调查精度结论。请在运行前检查输入数据的 CRS、时间范围、分辨率、NoData 和变量单位。
