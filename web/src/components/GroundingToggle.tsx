import { FileText, FileX } from 'lucide-react';

interface GroundingToggleProps {
  enabled: boolean;
  onToggle: (enabled: boolean) => void;
}

export default function GroundingToggle({ enabled, onToggle }: GroundingToggleProps) {
  return (
    <div className="flex items-center gap-2">
      <div className="flex items-center gap-1.5 text-sm">
        {enabled ? (
          <FileText className="w-4 h-4 text-green-300" />
        ) : (
          <FileX className="w-4 h-4 text-gray-400" />
        )}
        <span className="hidden sm:inline text-purple-200">Document Grounding</span>
      </div>
      
      <button
        onClick={() => onToggle(!enabled)}
        className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors ${
          enabled ? 'bg-green-500' : 'bg-gray-400'
        }`}
        role="switch"
        aria-checked={enabled}
      >
        <span
          className={`inline-block h-4 w-4 transform rounded-full bg-white transition-transform ${
            enabled ? 'translate-x-6' : 'translate-x-1'
          }`}
        />
      </button>
    </div>
  );
}
