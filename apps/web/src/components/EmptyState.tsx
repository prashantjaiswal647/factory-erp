type EmptyStateProps = {
  title: string;
  message: string;
};

export default function EmptyState({ title, message }: EmptyStateProps) {
  return (
    <div className="flex min-h-40 flex-col items-center justify-center px-4 text-center">
      <p className="text-sm font-medium text-zinc-700">{title}</p>
      <p className="mt-1 max-w-md text-sm text-zinc-500">{message}</p>
    </div>
  );
}
