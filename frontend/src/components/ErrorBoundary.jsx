import { Component } from 'react'


export default class ErrorBoundary extends Component {
  state = { error: null }

  static getDerivedStateFromError(error) { return { error } }

  componentDidCatch(error, info) {
    if (import.meta.env.DEV) console.error('UI error caught by ErrorBoundary:', error, info?.componentStack)
  }

  render() {
    if (!this.state.error) return this.props.children
    return (
      <div className="container" style={{ padding: '60px 20px' }}>
        <div className="notice error" role="alert">
          <div>
            <strong>Something went wrong on this page.</strong>
            <div className="muted-sm">Your data is safe. Try again, or go back to the home page.</div>
          </div>
          <div className="row-gap">
            <button className="btn btn-primary" onClick={() => this.setState({ error: null })}>Try again</button>
            <a className="btn btn-ghost" href="/">Home</a>
          </div>
        </div>
      </div>
    )
  }
}
