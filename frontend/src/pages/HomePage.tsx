import { useState, useEffect } from 'react'
import { Users, MessageSquare, ThumbsUp, FileText, Activity, TrendingUp, Zap, Shield, Bug, Eye, CheckCircle2 } from 'lucide-react'
import { getDatabases, getDatabaseStats, DatabaseStats, getControlFlags, setModerationFlag, ControlFlags } from '../services/api'
import DatabaseSelector from '../components/DatabaseSelector'

export default function HomePage() {
  const [databases, setDatabases] = useState<string[]>([])
  const [selectedDb, setSelectedDb] = useState<string>('')
  const [stats, setStats] = useState<DatabaseStats>({
    activeUsers: 0,
    totalPosts: 0,
    totalComments: 0,
    totalLikes: 0,
  })
  const [loading, setLoading] = useState(false)

  // 控制标志状态
  const [controlFlags, setControlFlags] = useState<ControlFlags>({
    attack_enabled: false,
    aftercare_enabled: false,
    auto_status: false,
    moderation_enabled: false,
  })
  const [loadingFlags, setLoadingFlags] = useState(false)

  // 加载控制标志
  useEffect(() => {
    const loadControlFlags = async () => {
      try {
        const flags = await getControlFlags()
        setControlFlags(flags)
      } catch (error) {
        console.error('Failed to load control flags:', error)
      }
    }
    loadControlFlags()
    // 定期刷新控制标志状态
    const interval = setInterval(loadControlFlags, 5000)
    return () => clearInterval(interval)
  }, [])

  // 加载数据库列表
  useEffect(() => {
    const loadDatabases = async () => {
      const dbs = await getDatabases()
      setDatabases(dbs)
      if (dbs.length > 0) {
        setSelectedDb(dbs[0])
      }
    }
    loadDatabases()
  }, [])

  // 加载统计数据
  useEffect(() => {
    if (selectedDb) {
      const loadStats = async () => {
        setLoading(true)
        const data = await getDatabaseStats(selectedDb)
        setStats(data)
        setLoading(false)
      }
      loadStats()
    }
  }, [selectedDb])

  const statsCards = [
    { label: '活跃用户', value: stats.activeUsers, icon: Users, color: 'from-blue-500 to-cyan-500' },
    { label: '发布内容', value: stats.totalPosts, icon: FileText, color: 'from-purple-500 to-blue-500' },
    { label: '用户评论', value: stats.totalComments, icon: MessageSquare, color: 'from-cyan-500 to-green-500' },
    { label: '互动点赞', value: stats.totalLikes, icon: ThumbsUp, color: 'from-green-500 to-emerald-500' },
  ]

  const features = [
    {
      title: '实时监控',
      description: '7x24小时监控网络舆论动态，及时发现极端内容',
      icon: Activity,
      gradient: 'from-blue-500 to-cyan-500',
    },
    {
      title: '智能干预',
      description: '基于AI的多智能体协同干预，降低情绪对立',
      icon: Zap,
      gradient: 'from-purple-500 to-blue-500',
    },
    {
      title: '效果评估',
      description: '实时评估干预效果，动态调整策略',
      icon: TrendingUp,
      gradient: 'from-cyan-500 to-green-500',
    },
    {
      title: '关系图谱',
      description: '直观展示舆论走势和系统运行状态',
      icon: MessageSquare,
      gradient: 'from-green-500 to-emerald-500',
    },
  ]

  return (
    <div className="space-y-8">
      {/* 欢迎区域 */}
      <div className="glass-card p-8">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-5xl font-bold mb-2 bg-gradient-to-r from-blue-600 to-green-600 bg-clip-text text-transparent">
              欢迎使用 EvoCorps
            </h1>
            <p className="text-slate-600 text-xl">
              面向网络舆论去极化的进化式多智能体框架
            </p>
          </div>
          <img 
            src="/logot.png" 
            alt="EvoCorps Icon" 
            className="h-24 w-auto drop-shadow-xl transition-transform duration-300 hover:scale-110 cursor-pointer"
          />
        </div>
      </div>

      {/* 数据库选择 */}
      <div className="glass-card p-6">
        <div className="flex items-center gap-4">
          <DatabaseSelector
            databases={databases}
            selectedDb={selectedDb}
            onSelect={setSelectedDb}
            label="选择数据库："
          />
          {loading && <span className="text-base text-slate-500">加载中...</span>}
        </div>
      </div>

      {/* 系统控制面板 */}
      <div className="glass-card p-6">
        <div className="flex items-center gap-3 mb-4">
          <Zap size={24} className="text-purple-600" />
          <h2 className="text-xl font-bold text-slate-800">系统控制面板</h2>
        </div>
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
          {/* 审核系统开关 */}
          <ControlToggleCard
            title="内容审核"
            description="启用内容审核系统（可见性降级、警告标签、硬删除）"
            icon={Shield}
            iconGradient="from-red-500 to-orange-500"
            enabled={controlFlags.moderation_enabled}
            onToggle={async (enabled) => {
              setLoadingFlags(true)
              try {
                await setModerationFlag(enabled)
                setControlFlags(prev => ({ ...prev, moderation_enabled: enabled }))
              } catch (error) {
                alert(`操作失败: ${error}`)
              } finally {
                setLoadingFlags(false)
              }
            }}
            loading={loadingFlags}
          />
          {/* 恶意攻击开关 */}
          <ControlToggleCard
            title="恶意攻击"
            description="启用恶意机器人生成和攻击"
            icon={Bug}
            iconGradient="from-purple-500 to-pink-500"
            enabled={controlFlags.attack_enabled}
            onToggle={async (enabled) => {
              setLoadingFlags(true)
              try {
                await setAttackFlag(enabled)
                setControlFlags(prev => ({ ...prev, attack_enabled: enabled }))
              } catch (error) {
                alert(`操作失败: ${error}`)
              } finally {
                setLoadingFlags(false)
              }
            }}
            loading={loadingFlags}
          />
          {/* 事后干预开关 */}
          <ControlToggleCard
            title="事实核查"
            description="启用第三方事实核查系统"
            icon={Eye}
            iconGradient="from-blue-500 to-cyan-500"
            enabled={controlFlags.aftercare_enabled}
            onToggle={async (enabled) => {
              setLoadingFlags(true)
              try {
                await setAftercareFlag(enabled)
                setControlFlags(prev => ({ ...prev, aftercare_enabled: enabled }))
              } catch (error) {
                alert(`操作失败: ${error}`)
              } finally {
                setLoadingFlags(false)
              }
            }}
            loading={loadingFlags}
          />
          {/* 自动监控开关 */}
          <ControlToggleCard
            title="自动监控"
            description="启用舆论平衡自动监控和干预"
            icon={Activity}
            iconGradient="from-green-500 to-emerald-500"
            enabled={controlFlags.auto_status === true}
            onToggle={async (enabled) => {
              setLoadingFlags(true)
              try {
                await setAutoStatusFlag(enabled)
                setControlFlags(prev => ({ ...prev, auto_status: enabled }))
              } catch (error) {
                alert(`操作失败: ${error}`)
              } finally {
                setLoadingFlags(false)
              }
            }}
            loading={loadingFlags}
          />
        </div>
      </div>

      {/* 统计卡片 */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
        {statsCards.map((stat, index) => {
          const Icon = stat.icon
          return (
            <div key={index} className="glass-card p-6 hover:scale-105 transition-transform duration-200">
              <div className="flex items-center justify-between mb-4">
                <div className={`w-12 h-12 rounded-2xl bg-gradient-to-r ${stat.color} flex items-center justify-center shadow-lg`}>
                  <Icon size={24} className="text-white" />
                </div>
              </div>
              <p className="text-4xl font-bold text-slate-800 mb-1">{stat.value.toLocaleString()}</p>
              <p className="text-base text-slate-600">{stat.label}</p>
            </div>
          )
        })}
      </div>

      {/* 功能特性 */}
      <div>
        <h2 className="text-3xl font-bold text-slate-800 mb-6">核心功能</h2>
        <div className="grid grid-cols-1 md:grid-cols-4 gap-6">
          {features.map((feature, index) => {
            const Icon = feature.icon
            return (
              <div key={index} className="glass-card p-6 hover:scale-105 transition-transform duration-200">
                <div className={`w-14 h-14 rounded-2xl bg-gradient-to-r ${feature.gradient} flex items-center justify-center shadow-lg mb-4`}>
                  <Icon size={28} className="text-white" />
                </div>
                <h3 className="text-2xl font-semibold text-slate-800 mb-2">{feature.title}</h3>
                <p className="text-slate-600 text-base">{feature.description}</p>
              </div>
            )
          })}
        </div>
      </div>
    </div>
  )
}

// 控制开关卡片组件
interface ControlToggleCardProps {
  title: string
  description: string
  icon: ElementType
  iconGradient: string
  enabled: boolean
  onToggle: (enabled: boolean) => void
  loading?: boolean
}

function ControlToggleCard({ title, description, icon: Icon, iconGradient, enabled, onToggle, loading = false }: ControlToggleCardProps) {
  return (
    <div className={`glass-card p-5 transition-all duration-200 ${enabled ? 'ring-2 ring-green-400' : ''}`}>
      <div className="flex items-start justify-between mb-3">
        <div className={`w-12 h-12 rounded-xl bg-gradient-to-r ${iconGradient} flex items-center justify-center shadow-lg`}>
          <Icon size={24} className="text-white" />
        </div>
        <button
          onClick={() => onToggle(!enabled)}
          disabled={loading}
          className={`relative w-16 h-8 rounded-full transition-all duration-200 ${
            enabled ? 'bg-green-500' : 'bg-slate-300'
          } ${loading ? 'opacity-50 cursor-not-allowed' : 'cursor-pointer hover:scale-105'}`}
        >
          <div
            className={`absolute top-1 left-1 w-6 h-6 rounded-full bg-white shadow-md transition-transform duration-200 ${
              enabled ? 'translate-x-8' : 'translate-x-0'
            }`}
          />
        </button>
      </div>
      <h3 className="text-lg font-semibold text-slate-800 mb-1">{title}</h3>
      <p className="text-sm text-slate-600 mb-2">{description}</p>
      <div className="flex items-center gap-2 text-sm">
        {enabled ? (
          <>
            <CheckCircle2 size={16} className="text-green-600" />
            <span className="text-green-600 font-medium">已启用</span>
          </>
        ) : (
          <>
            <span className="text-slate-500">已禁用</span>
          </>
        )}
      </div>
    </div>
  )
}
