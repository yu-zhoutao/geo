import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'

import GeospatialContext from './GeospatialContext.vue'


describe('GeospatialContext', () => {
  it('keeps final artifacts and evidence summaries compact in the sidebar', () => {
    const wrapper = mount(GeospatialContext, {
      props: {
        artifacts: [
          { id: 'artifact-1', title: 'KDE 运行摘要', path: '/tmp/kde.md', analysis_type: 'kde', kind: 'report', description: 'desc' },
          { id: 'artifact-2', title: 'KDE 运行清单', path: '/tmp/manifest.json', analysis_type: 'kde', kind: 'manifest', description: 'manifest desc' },
          { id: 'artifact-3', title: 'FCD 数据核验报告', path: '/tmp/data_audit_report.txt', kind: 'text', description: 'audit desc' },
          { id: 'artifact-4', title: '空间整备汇总数据', path: '/tmp/spatial_prep_summary.json', kind: 'json', description: 'summary desc' },
        ],
        timelineEntries: [
          { id: 'evidence-1', kind: 'evidence', text: '参数快照', title: '参数快照', detail: '150m 网格', record_type: 'parameter_snapshot', created_at: '2026-04-21T10:00:00.000Z' },
          {
            id: 'evidence-2',
            kind: 'evidence',
            text: '数据画像',
            title: '数据画像',
            detail: 'FCD 点检查',
            record_type: 'dataset_profile',
            created_at: '2026-04-21T10:01:00.000Z',
            data: { feature_count: 60897, crs: 'EPSG:32650' },
            provenance: { command: 'uv run python scripts/audit.py' },
          },
        ],
      },
    })

    expect(wrapper.text()).not.toContain('验证状态')
    expect(wrapper.text()).not.toContain('已设置统一投影')
    expect(wrapper.text()).not.toContain('检测到 CRS 不一致')
    expect(wrapper.find('[data-testid="sidebar-artifact-open-artifact-1"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="sidebar-artifact-preview-artifact-1"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="sidebar-artifact-preview-artifact-2"]').exists()).toBe(false)
    expect(wrapper.text().indexOf('工作区产物')).toBeLessThan(wrapper.text().indexOf('地理任务摘要'))
    expect(wrapper.text()).not.toContain('暂无地理任务摘要。')
    expect(wrapper.text()).toContain('数据画像')
    expect(wrapper.text()).toContain('参数快照')
    expect(wrapper.find('[data-testid="evidence-card-evidence-1"]').exists()).toBe(true)
    expect(wrapper.get('[data-testid="artifact-card-artifact-1"]').classes()).toEqual(expect.arrayContaining(['rounded-lg', 'border', 'border-slate-200/70', 'bg-white', 'shadow-sm']))
    expect(wrapper.get('[data-testid="artifact-kind-artifact-1"]').classes()).toEqual(expect.arrayContaining(['rounded-full', 'bg-slate-100']))
    expect(wrapper.get('[data-testid="evidence-card-evidence-2"]').classes()).toEqual(expect.arrayContaining(['rounded-lg', 'border', 'border-slate-200/70', 'bg-white', 'shadow-sm']))
    expect(wrapper.get('[data-testid="evidence-kind-evidence-2"]').classes()).toEqual(expect.arrayContaining(['rounded-full', 'bg-slate-100']))
    expect(wrapper.text()).toContain('运行清单')
    expect(wrapper.text()).toContain('文本')
    expect(wrapper.text()).toContain('JSON')
    expect(wrapper.text()).not.toContain('可用数据集')
    expect(wrapper.text()).not.toContain('只保留当前任务的少量全局上下文与最终产物摘要')
  })

  it('uses expandable evidence entries as the task summary', async () => {
    const wrapper = mount(GeospatialContext, {
      props: {
        artifacts: [],
        timelineEntries: [
          {
            id: 'evidence-1',
            kind: 'evidence',
            text: '制图诚实性检查',
            title: '制图诚实性检查',
            detail: '确认比例尺与投影说明完整',
            record_type: 'verification_fact',
            created_at: '2026-04-21T10:00:00.000Z',
            data: {
              status: 'passed',
              reason_code: 'map_honesty_checked',
              checked_inputs: ['haidian_heatmap.png', 'haidian_kde_density.tif'],
              conclusion: '地图标注和投影说明可复核。',
            },
            provenance: { command: 'uv run python scripts/review_map.py' },
          },
          { id: 'evidence-2', kind: 'evidence', text: 'KDE密度栅格统计验证', title: 'KDE密度栅格统计验证', detail: null, record_type: 'verification_fact', created_at: '2026-04-21T10:01:00.000Z' },
        ],
      },
    })

    expect(wrapper.text()).not.toContain('暂无地理任务摘要。')
    expect(wrapper.get('[data-testid="evidence-card-evidence-1"]').classes()).toEqual(expect.arrayContaining(['rounded-lg', 'border', 'bg-white', 'shadow-sm']))
    expect(wrapper.get('[data-testid="evidence-card-evidence-2"]').classes()).toEqual(expect.arrayContaining(['rounded-lg', 'border', 'bg-white', 'shadow-sm']))
    expect(wrapper.get('[data-testid="evidence-toggle-evidence-1"]').attributes('aria-expanded')).toBe('false')
    expect(wrapper.find('[data-testid="evidence-details-evidence-1"]').exists()).toBe(false)

    await wrapper.get('[data-testid="evidence-toggle-evidence-1"]').trigger('click')

    expect(wrapper.get('[data-testid="evidence-toggle-evidence-1"]').attributes('aria-expanded')).toBe('true')
    expect(wrapper.get('[data-testid="evidence-details-evidence-1"]').text()).toContain('checked_inputs')
    expect(wrapper.get('[data-testid="evidence-details-evidence-1"]').text()).toContain('haidian_heatmap.png')
    expect(wrapper.get('[data-testid="evidence-details-evidence-1"]').text()).not.toContain('记录')
    expect(wrapper.get('[data-testid="evidence-details-evidence-1"]').text()).not.toContain('时间')
    expect(wrapper.get('[data-testid="evidence-details-evidence-1"]').text()).not.toContain('数据')
    expect(wrapper.get('[data-testid="evidence-details-evidence-1"]').text()).not.toContain('来源')
    expect(wrapper.get('[data-testid="evidence-details-evidence-1"]').text()).not.toContain('uv run python scripts/review_map.py')
  })

  it('labels interpolation and hotspot artifacts and evidence distinctly', () => {
    const wrapper = mount(GeospatialContext, {
      props: {
        artifacts: [
          { id: 'artifact-idw', title: 'IDW 插值栅格', path: '/tmp/idw.tif', analysis_type: 'spatial_interpolation', kind: 'raster', description: 'desc' },
          { id: 'artifact-gistar', title: 'Gi* 统计表', path: '/tmp/gistar.csv', analysis_type: 'spatial_hotspot', kind: 'table', description: 'desc' },
        ],
        timelineEntries: [
          {
            id: 'evidence-idw',
            kind: 'evidence',
            text: 'IDW 参数快照',
            title: 'IDW 参数快照',
            record_type: 'parameter_snapshot',
            created_at: '2026-04-21T10:00:00.000Z',
            data: { analysis_type: 'spatial_interpolation', power: 2 },
          },
          {
            id: 'evidence-gistar',
            kind: 'evidence',
            text: 'Gi* 权重元数据',
            title: 'Gi* 权重元数据',
            record_type: 'verification_fact',
            created_at: '2026-04-21T10:01:00.000Z',
            provenance: { analysis_type: 'spatial_hotspot', weights: 'queen' },
          },
        ],
      },
    })

    expect(wrapper.get('[data-testid="artifact-analysis-type-artifact-idw"]').text()).toBe('IDW 插值')
    expect(wrapper.get('[data-testid="artifact-analysis-type-artifact-gistar"]').text()).toBe('Gi* 热点')
    expect(wrapper.get('[data-testid="artifact-kind-artifact-idw"]').text()).toBe('栅格')
    expect(wrapper.get('[data-testid="evidence-analysis-type-evidence-idw"]').text()).toBe('IDW 插值')
    expect(wrapper.get('[data-testid="evidence-analysis-type-evidence-gistar"]').text()).toBe('Gi* 热点')
  })
})
