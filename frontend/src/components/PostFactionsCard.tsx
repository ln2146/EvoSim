import { useState, useEffect } from 'react'
import { GitBranch, RefreshCw } from 'lucide-react'
import { getDatabases, getPostFactions, PostFactionsSummary } from '../services/api'

export default function PostFactionsCard() {
  const [postFactions, setPostFactions] = useState<PostFactionsSummary | null>(null)
  const [loading, setLoading] = useState(false)
  const [dbName, setDbName] = useState<string>('')

  useEffect(() => {
    const init = async () => {
      const dbs = await getDatabases()
      if (dbs.length > 0) {
        setDbName(dbs[0])
      }
    }
    init()
  }, [])

  useEffect(() => {
    if (dbName) loadFactions()
  }, [dbName])

  const loadFactions = async () => {
    setLoading(true)
    try {
      const data = await getPostFactions(dbName, 50, 0)
      setPostFactions(data)
    } catch (error) {
      console.error('Failed to load factions data:', error)
    } finally {
      setLoading(false)
    }
  }

  if (!postFactions) {
    return (
      <div className="glass-card p-6">
        <div className="flex items-center gap-3 mb-4">
          <div className="w-10 h-10 rounded-xl bg-gradient-to-r from-purple-500 to-blue-500 flex items-center justify-center">
            <GitBranch size={20} className="text-white" />
          </div>
          <h2 className="text-2xl font-bold text-slate-800">帖子派系分布分析</h2>
        </div>
        <p className="text-sm text-slate-500">{loading ? '加载中...' : '暂无数据'}</p>
      </div>
    )
  }

  return (
    <div className="glass-card p-6">
      <div className="flex items-center justify-between mb-6">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl bg-gradient-to-r from-purple-500 to-blue-500 flex items-center justify-center">
            <GitBranch size={20} className="text-white" />
          </div>
          <h2 className="text-2xl font-bold text-slate-800">帖子派系分布分析</h2>
        </div>
        <button
          onClick={loadFactions}
          disabled={loading}
          className="flex items-center gap-2 px-3 py-2 rounded-lg bg-slate-100 hover:bg-slate-200 text-slate-600 text-sm font-medium transition-colors disabled:opacity-50"
        >
          <RefreshCw size={14} className={loading ? 'animate-spin' : ''} />
          刷新
        </button>
      </div>

      {postFactions.total_posts_analyzed === 0 ? (
        <div className="p-6 bg-yellow-50 border border-yellow-200 rounded-xl">
          <p className="text-yellow-800">暂无符合条件的数据（需要至少3条评论的帖子）</p>
        </div>
      ) : (
        <>
          {/* 汇总指标 */}
          <div className="grid grid-cols-4 gap-4 mb-6">
            <div className="p-4 rounded-xl bg-gradient-to-br from-purple-600 to-blue-500 text-white">
              <p className="text-3xl font-bold mb-1">{postFactions.total_posts_analyzed}</p>
              <p className="text-sm opacity-90">分析帖子数</p>
            </div>
            <div className="p-4 rounded-xl bg-gradient-to-br from-green-500 to-emerald-500 text-white">
              <p className="text-3xl font-bold mb-1">{(postFactions.avg_support_ratio * 100).toFixed(1)}%</p>
              <p className="text-sm opacity-90">平均赞成比例</p>
            </div>
            <div className="p-4 rounded-xl bg-gradient-to-br from-gray-400 to-gray-500 text-white">
              <p className="text-3xl font-bold mb-1">{(postFactions.avg_neutral_ratio * 100).toFixed(1)}%</p>
              <p className="text-sm opacity-90">平均中立比例</p>
            </div>
            <div className="p-4 rounded-xl bg-gradient-to-br from-red-500 to-orange-500 text-white">
              <p className="text-3xl font-bold mb-1">{(postFactions.avg_oppose_ratio * 100).toFixed(1)}%</p>
              <p className="text-sm opacity-90">平均反对比例</p>
            </div>
          </div>

          {/* 特殊帖子 */}
          <div className="grid grid-cols-3 gap-4 mb-6">
            {postFactions.hottest_post && (
              <div className="p-4 rounded-xl bg-gradient-to-br from-orange-50 to-red-50 border-2 border-orange-300">
                <p className="text-sm text-orange-700 mb-2 font-semibold">🔥 最火帖子</p>
                <p className="text-lg font-bold text-slate-800 mb-1">{postFactions.hottest_post.post_id}</p>
                <div className="flex gap-3 text-sm text-slate-600 mb-2">
                  <span>互动: {postFactions.hottest_post.total_interactions}</span>
                </div>
                <div className="flex gap-3 text-xs text-slate-600">
                  <span className="text-green-600">支持 {(postFactions.hottest_post.support_ratio * 100).toFixed(1)}%</span>
                  <span className="text-gray-600">中立 {(postFactions.hottest_post.neutral_ratio * 100).toFixed(1)}%</span>
                  <span className="text-red-600">反对 {(postFactions.hottest_post.oppose_ratio * 100).toFixed(1)}%</span>
                </div>
              </div>
            )}
            {postFactions.most_divisive_post && (
              <div className="p-4 rounded-xl bg-slate-50 border border-slate-200">
                <p className="text-sm text-slate-600 mb-2">最具分歧帖子</p>
                <p className="text-lg font-bold text-slate-800 mb-1">{postFactions.most_divisive_post.post_id}</p>
                <div className="flex gap-4 text-sm text-slate-600">
                  <span>赞成: {(postFactions.most_divisive_post.support_ratio * 100).toFixed(1)}%</span>
                  <span>反对: {(postFactions.most_divisive_post.oppose_ratio * 100).toFixed(1)}%</span>
                  <span>互动: {postFactions.most_divisive_post.total_interactions || postFactions.most_divisive_post.total_comments || '-'}</span>
                </div>
              </div>
            )}
            {postFactions.most_consensus_post && (
              <div className="p-4 rounded-xl bg-slate-50 border border-slate-200">
                <p className="text-sm text-slate-600 mb-2">最具共识帖子</p>
                <p className="text-lg font-bold text-slate-800 mb-1">{postFactions.most_consensus_post.post_id}</p>
                <div className="flex gap-4 text-sm text-slate-600">
                  <span>主导: {postFactions.most_consensus_post.dominant_stance === 'support' ? '赞成' :
                             postFactions.most_consensus_post.dominant_stance === 'oppose' ? '反对' : '中立'}</span>
                  <span>比例: {(postFactions.most_consensus_post.ratio * 100).toFixed(1)}%</span>
                  <span>互动: {postFactions.most_consensus_post.total_interactions || postFactions.most_consensus_post.total_comments || '-'}</span>
                </div>
              </div>
            )}
          </div>

          {/* 帖子派系列表 */}
          <div>
            <h3 className="text-xl font-bold text-slate-800 mb-4">帖子派系分布详情</h3>

            <div className="space-y-4 max-h-[600px] overflow-y-auto">
              {(postFactions.post_stances || postFactions.post_factions || []).map((post) => {
                const totalForCalculation = post.total_comments ?? post.total_interactions;
                const supportCount = post.support_count ?? Math.round((post.support_ratio || 0) * totalForCalculation);
                const neutralCount = post.neutral_count ?? Math.round((post.neutral_ratio || 0) * totalForCalculation);
                const opposeCount = post.oppose_count ?? Math.round((post.oppose_ratio || 0) * totalForCalculation);

                let dominantStance = '中立';
                let dominantColor = 'bg-gray-100 text-gray-700';
                if ((post.support_ratio || 0) >= 0.4) {
                  dominantStance = '支持主导';
                  dominantColor = 'bg-green-100 text-green-700';
                } else if ((post.oppose_ratio || 0) >= 0.4) {
                  dominantStance = '反对主导';
                  dominantColor = 'bg-red-100 text-red-700';
                }

                return (
                  <div
                    key={post.post_id}
                    className={`p-5 rounded-xl bg-white border shadow-sm hover:shadow-md transition-shadow ${
                      post.is_hottest ? 'border-orange-400 border-2' : 'border-slate-200'
                    }`}
                  >
                    <div className="flex items-start justify-between mb-4">
                      <div className="flex-1">
                        <div className="flex items-center gap-2 mb-2">
                          <h4 className="text-lg font-bold text-slate-800">{post.post_id}</h4>
                          <span className={`px-2 py-1 text-xs rounded-full font-medium ${dominantColor}`}>
                            {dominantStance}
                          </span>
                          {post.is_hottest && (
                            <span className="px-2 py-1 bg-gradient-to-r from-orange-500 to-red-500 text-white text-xs rounded-full font-bold">
                              🔥 最火
                            </span>
                          )}
                        </div>
                        <p className="text-sm text-slate-600">总评论数: {post.total_comments ?? post.total_interactions}</p>
                      </div>
                      <div className="flex gap-2">
                        <span className="px-3 py-1 bg-green-100 text-green-700 text-xs rounded-full font-medium">
                          支持 {supportCount}条
                        </span>
                        <span className="px-3 py-1 bg-gray-100 text-gray-700 text-xs rounded-full font-medium">
                          中立 {neutralCount}条
                        </span>
                        <span className="px-3 py-1 bg-red-100 text-red-700 text-xs rounded-full font-medium">
                          反对 {opposeCount}条
                        </span>
                      </div>
                    </div>

                    {/* 派系比例可视化 */}
                    <div className="mb-4">
                      <div className="h-6 rounded-full overflow-hidden flex">
                        <div
                          className="bg-green-500 flex items-center justify-center text-white text-xs font-medium"
                          style={{ width: `${(post.support_ratio || 0) * 100}%` }}
                        >
                          {(post.support_ratio || 0) >= 0.1 ? `${((post.support_ratio || 0) * 100).toFixed(0)}%` : ''}
                        </div>
                        <div
                          className="bg-gray-400 flex items-center justify-center text-white text-xs font-medium"
                          style={{ width: `${(post.neutral_ratio || 0) * 100}%` }}
                        >
                          {(post.neutral_ratio || 0) >= 0.1 ? `${((post.neutral_ratio || 0) * 100).toFixed(0)}%` : ''}
                        </div>
                        <div
                          className="bg-red-500 flex items-center justify-center text-white text-xs font-medium"
                          style={{ width: `${(post.oppose_ratio || 0) * 100}%` }}
                        >
                          {(post.oppose_ratio || 0) >= 0.1 ? `${((post.oppose_ratio || 0) * 100).toFixed(0)}%` : ''}
                        </div>
                      </div>
                    </div>

                    {/* 高影响力用户 */}
                    {post.high_influence_users && post.high_influence_users.length > 0 && (
                      <div className="pt-3 border-t border-slate-200">
                        <p className="text-xs text-slate-600 mb-2">高影响力用户（互动度最高）:</p>
                        <div className="flex flex-wrap gap-2">
                          {post.high_influence_users.slice(0, 5).map((user, idx) => (
                            <span
                              key={idx}
                              className={`px-2 py-1 rounded text-xs font-mono ${
                                user.stance === 'support' ? 'bg-green-100 text-green-700' :
                                user.stance === 'oppose' ? 'bg-red-100 text-red-700' :
                                'bg-gray-100 text-gray-700'
                              }`}
                            >
                              {user.user_id.slice(-6)} ({user.stance === 'support' ? '支持' :
                                user.stance === 'oppose' ? '反对' : '中立'}) [{user.score.toFixed(2)}]
                            </span>
                          ))}
                        </div>
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          </div>
        </>
      )}
    </div>
  )
}
