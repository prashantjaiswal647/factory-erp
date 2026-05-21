type EmptyStateProps = {
  title: string;
  message: string;
};

export default function EmptyState({ title, message }: EmptyStateProps) {
  return (
    <div className="flex min-h-40 flex-col items-center justify-center px-4 text-center">
      <p className="text-sm font-medium text-[#111827]">{title}</p>
      <p className="mt-1 max-w-md text-sm text-[#4B5563]">{message}</p>
    </div>
  );
}
