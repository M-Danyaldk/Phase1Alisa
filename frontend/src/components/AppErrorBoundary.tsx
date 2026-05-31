import { Component, ErrorInfo, ReactNode } from 'react';

type Props = {
  children: ReactNode;
};

type State = {
  hasError: boolean;
};

export class AppErrorBoundary extends Component<Props, State> {
  state: State = { hasError: false };

  static getDerivedStateFromError(): State {
    return { hasError: true };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error('MsAlisia frontend error boundary caught an error.', {
      message: error.message,
      componentStack: info.componentStack,
    });
  }

  render() {
    if (this.state.hasError) {
      return <main className="error-boundary-page">
        <section className="legal-card">
          <span>MsAlisia</span>
          <h1>Something went wrong.</h1>
          <p>Please refresh the page or contact support if it continues.</p>
          <button className="primary-button" type="button" onClick={() => window.location.reload()}>Refresh Page</button>
        </section>
      </main>;
    }
    return this.props.children;
  }
}
