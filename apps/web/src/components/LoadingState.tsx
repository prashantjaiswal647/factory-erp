import { Loader2 } from "lucide-react";

type LoadingStateProps = {
  label?: string;
};

export default function LoadingState({ label = "Loading data..." }: LoadingStateProps) {
  return (
    <div className="flex min-h-40 items-center justify-center gap-2 text-sm text-[#4B5563]">
      <Loader2 className="h-4 w-4 animate-spin text-[#6D28D9]" aria-hidden="true" />
      {label}
    </div>
  );
}
