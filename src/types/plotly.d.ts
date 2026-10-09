declare module "plotly.js-dist-min" {
  interface PlotlyStatic {
    react(el: HTMLElement, data: unknown[], layout?: Record<string, unknown>, config?: Record<string, unknown>): Promise<unknown>;
    purge(el: HTMLElement): void;
  }
  const Plotly: PlotlyStatic & { default?: PlotlyStatic };
  export default Plotly;
}
