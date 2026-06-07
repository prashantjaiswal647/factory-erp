import React, { Component, ErrorInfo, ReactNode } from "react";

interface Props {
  children?: ReactNode;
  fallback?: ReactNode;
  name?: string;
}

interface State {
  hasError: boolean;
}

export class WidgetErrorBoundary extends Component<Props, State> {
  public state: State = {
    hasError: false
  };

  public static getDerivedStateFromError(_: Error): State {
    return { hasError: true };
  }

  public componentDidCatch(error: Error, errorInfo: ErrorInfo) {
    console.error(`ErrorBoundary caught an error in widget [${this.props.name || "Unknown"}]:`, error, errorInfo);
  }

  public render() {
    if (this.state.hasError) {
      return (
        this.props.fallback || (
          <section className="rounded-xl border border-zinc-200 bg-zinc-50 p-4 text-center">
            <p className="text-xs font-semibold text-zinc-500 uppercase tracking-wide">
              {this.props.name || "Card"}
            </p>
            <p className="mt-1 text-sm text-zinc-600">Data not available yet</p>
          </section>
        )
      );
    }

    return this.props.children;
  }
}
