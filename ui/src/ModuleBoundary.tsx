import { Component, type ReactNode } from "react";

/** A module view that throws shows its error in place instead of blanking the whole dashboard. */
export default class ModuleBoundary extends Component<{ name: string; children: ReactNode }, { error: Error | null }> {
  state = { error: null as Error | null };

  static getDerivedStateFromError(error: Error) {
    return { error };
  }

  render() {
    if (!this.state.error) return this.props.children;
    return (
      <div className="card empty">
        <b>The {this.props.name} view crashed</b>
        <pre className="err">{String(this.state.error.stack ?? this.state.error)}</pre>
        <button onClick={() => this.setState({ error: null })}>Try again</button>
      </div>
    );
  }
}
