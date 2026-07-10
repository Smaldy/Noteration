import { Component, type ReactNode } from "react";
import { useTranslation } from "react-i18next";

import { Button } from "@/components/ui/button";

/**
 * Last-resort catch for a render crash anywhere in the app. Without it a single
 * thrown render (e.g. a page whose module fails to evaluate in the desktop
 * webview) unmounts the whole tree, leaving a dead white window with no way to
 * navigate away short of killing the app. The fallback offers a full reload back
 * to the library, which resets whatever state triggered the crash.
 */
export class AppErrorBoundary extends Component<
  { children: ReactNode },
  { error: Error | null }
> {
  state: { error: Error | null } = { error: null };

  static getDerivedStateFromError(error: Error) {
    return { error };
  }

  render() {
    if (this.state.error) return <CrashScreen error={this.state.error} />;
    return this.props.children;
  }
}

function CrashScreen({ error }: { error: Error }) {
  const { t } = useTranslation();
  return (
    <div className="flex min-h-screen flex-col items-center justify-center gap-4 px-6 text-center">
      <h1 className="font-display text-2xl font-semibold">
        {t("errorScreen.title")}
      </h1>
      <p className="max-w-md text-sm text-muted-foreground">
        {t("errorScreen.description")}
      </p>
      <p className="max-w-md break-all font-mono text-xs text-muted-foreground/70">
        {error.message}
      </p>
      <Button onClick={() => window.location.assign("/")}>
        {t("errorScreen.backToLibrary")}
      </Button>
    </div>
  );
}
