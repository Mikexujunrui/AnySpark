import { Component } from 'react'

export default class ErrorBoundary extends Component {
  constructor(props) {
    super(props)
    this.state = { error: null, info: null }
  }

  static getDerivedStateFromError(error) {
    return { error }
  }

  componentDidCatch(error, info) {
    this.setState({ info })
    if (typeof this.props.onError === 'function') {
      this.props.onError(error, info)
    }
  }

  render() {
    if (this.state.error) {
      return (
        <div className="min-h-screen flex items-center justify-center bg-zinc-950">
          <div className="text-center p-8 max-w-md">
            <div className="w-12 h-12 rounded-full bg-red-900/30 border border-red-700/50 flex items-center justify-center mx-auto mb-4">
              <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="text-red-400">
                <circle cx="12" cy="12" r="10"/>
                <line x1="12" y1="8" x2="12" y2="12"/>
                <line x1="12" y1="16" x2="12.01" y2="16"/>
              </svg>
            </div>
            <h2 className="text-lg font-semibold text-zinc-200 mb-2">页面出现错误</h2>
            <p className="text-sm text-zinc-400 mb-4 break-all">
              {this.state.error?.message || '未知错误'}
            </p>
            <div className="flex gap-3 justify-center">
              <button
                onClick={() => window.location.reload()}
                className="bg-zinc-800 hover:bg-zinc-700 text-zinc-200 px-4 py-2 rounded-lg text-sm transition-colors"
              >
                刷新页面
              </button>
              <button
                onClick={() => window.location.href = '/'}
                className="bg-accent hover:bg-accent-hover text-white px-4 py-2 rounded-lg text-sm transition-colors"
              >
                返回书架
              </button>
            </div>
          </div>
        </div>
      )
    }

    return this.props.children
  }
}