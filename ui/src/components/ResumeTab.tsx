import { useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { getResume, uploadResume, deleteResume, type ParsedResume } from "@/lib/api";

function ResumeCard({ resume, onDelete, deleting }: { resume: ParsedResume; onDelete: () => void; deleting: boolean }) {
  const isText = resume.filename.endsWith(".txt");
  return (
    <div className="bg-[#20201f] p-8 rounded-xl ghost-border relative overflow-hidden group hover:bg-[#2c2c2c] transition-colors">
      {/* Verified icon on hover */}
      <div className="absolute top-0 right-0 p-4 opacity-20 group-hover:opacity-100 transition-opacity">
        <button
          onClick={onDelete}
          disabled={deleting}
          className="material-symbols-outlined text-[#ff6e84] cursor-pointer disabled:opacity-40"
          title="Remove resume"
        >
          delete
        </button>
      </div>

      {/* Header: icon + filename + date */}
      <div className="flex items-start gap-6 mb-8">
        <div className="w-14 h-14 bg-[#262626] rounded-xl flex items-center justify-center ghost-border shrink-0">
          <span className="material-symbols-outlined text-[#a3a6ff] text-3xl">
            {isText ? "text_snippet" : "picture_as_pdf"}
          </span>
        </div>
        <div className="min-w-0">
          <h4 className="text-xl font-bold tracking-tight mb-1 truncate">{resume.filename}</h4>
          <p className="text-xs font-['Space_Grotesk'] uppercase tracking-widest text-[#adaaaa]">
            Processed: {new Date(resume.parsed_at).toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" })}
            {" \u2022 "}
            {new Date(resume.parsed_at).toLocaleTimeString("en-US", { hour: "2-digit", minute: "2-digit", timeZoneName: "short" })}
          </p>
        </div>
      </div>

      <div className="space-y-6">
        {/* Extracted Roles & Titles */}
        {resume.job_titles.length > 0 && (
          <div>
            <p className="text-[10px] font-['Space_Grotesk'] uppercase tracking-[0.2em] text-[#adaaaa] mb-3">
              Extracted Roles &amp; Titles
            </p>
            <div className="flex flex-wrap gap-2">
              {resume.job_titles.map((t, i) => (
                <span
                  key={t}
                  className={`px-3 py-1 font-['Space_Grotesk'] text-xs rounded-sm ${
                    i === 0
                      ? "bg-[#f5f2ff] text-[#5a5a71] font-bold border-l-2 border-[#a3a6ff]"
                      : "bg-[#262626] text-[#adaaaa] ghost-border"
                  }`}
                >
                  {t}
                </span>
              ))}
            </div>
          </div>
        )}

        {/* Key Technologies */}
        {resume.skills.length > 0 && (
          <div>
            <p className="text-[10px] font-['Space_Grotesk'] uppercase tracking-[0.2em] text-[#adaaaa] mb-3">
              Key Technologies
            </p>
            <div className="flex flex-wrap gap-2">
              {resume.skills.slice(0, 8).map((s) => (
                <span
                  key={s}
                  className="px-3 py-1 bg-[#00687a]/20 text-[#53ddfc] font-['Space_Grotesk'] text-xs rounded-full border border-[#53ddfc]/20"
                >
                  {s}
                </span>
              ))}
              {resume.skills.length > 8 && (
                <span className="px-3 py-1 bg-[#262626] text-[#adaaaa] font-['Space_Grotesk'] text-xs rounded-full ghost-border">
                  +{resume.skills.length - 8} more
                </span>
              )}
            </div>
          </div>
        )}

        {/* Footer */}
        <div className="pt-4 flex items-center justify-end">
          <button className="text-[#40ceed] text-xs font-['Space_Grotesk'] uppercase tracking-widest border-b border-transparent hover:border-[#40ceed] transition-all cursor-pointer">
            View Full Analysis
          </button>
        </div>
      </div>
    </div>
  );
}

export function ResumeTab() {
  const qc = useQueryClient();
  const inputRef = useRef<HTMLInputElement>(null);
  const [dragging, setDragging] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const { data: existing } = useQuery({
    queryKey: ["resume"],
    queryFn: getResume,
    retry: false,
  });

  const upload = useMutation({
    mutationFn: uploadResume,
    onSuccess: (data) => {
      qc.setQueryData(["resume"], data);
      setError(null);
    },
    onError: (err: { response?: { data?: { detail?: string } }; message: string }) => {
      setError(err.response?.data?.detail ?? err.message);
    },
  });

  const remove = useMutation({
    mutationFn: deleteResume,
    onSuccess: (data) => {
      qc.setQueryData(["resume"], data);
    },
  });

  const handleFile = (file: File | undefined) => {
    if (!file) return;
    if (!file.name.endsWith(".txt")) {
      setError("Only .txt resume files are supported.");
      return;
    }
    setError(null);
    upload.mutate(file);
  };

  const resumes = upload.data?.resumes ?? existing?.resumes ?? [];

  return (
    <div className="space-y-16">
      {/* Hero Section */}
      <header className="space-y-4">
        <h1 className="text-6xl md:text-7xl font-black tracking-tight leading-none">
          Craft <span className="text-[#a3a6ff]">Resume</span>
        </h1>
        <p className="text-[#adaaaa] text-lg max-w-2xl leading-relaxed">
          Upload your professional footprint. Our neural engine will dissect your
          expertise and prepare your profile for high-frequency matching.
        </p>
      </header>

      {/* Upload Section */}
      <section className="relative group">
        <div className="absolute -inset-1 pulse-gradient opacity-20 blur-xl group-hover:opacity-30 transition-opacity rounded-3xl" />
        <div
          className={`relative min-h-[400px] flex flex-col items-center justify-center p-12 rounded-3xl border-2 border-dashed transition-all cursor-pointer ${
            dragging
              ? "border-[#a3a6ff]/60 bg-[#a3a6ff]/10"
              : "border-[#484847]/30 hover:border-[#a3a6ff]/50"
          } ${upload.isPending ? "pointer-events-none opacity-60" : ""}`}
          onClick={() => inputRef.current?.click()}
          onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
          onDragLeave={() => setDragging(false)}
          onDrop={(e) => {
            e.preventDefault();
            setDragging(false);
            handleFile(e.dataTransfer.files[0]);
          }}
        >
          <input
            ref={inputRef}
            type="file"
            accept=".txt"
            className="hidden"
            onChange={(e) => handleFile(e.target.files?.[0])}
          />

          {upload.isPending ? (
            <>
              <div className="h-10 w-10 animate-spin rounded-full border-4 border-[#a3a6ff] border-t-transparent mb-4" />
              <p className="text-[#adaaaa]">Parsing resume...</p>
            </>
          ) : (
            <>
              <div className="w-24 h-24 pulse-gradient rounded-3xl flex items-center justify-center mb-8 shadow-2xl shadow-[#a3a6ff]/20">
                <span className="material-symbols-outlined text-white text-4xl" style={{ fontVariationSettings: "'FILL' 1" }}>
                  upload_file
                </span>
              </div>
              <h3 className="text-2xl font-bold mb-3 tracking-tight">Drop your dossier here</h3>
              <p className="text-[#adaaaa] font-['Space_Grotesk'] text-sm uppercase tracking-widest mb-10">
                TXT files up to 10MB
              </p>
              <button
                type="button"
                className="px-10 py-4 pulse-gradient rounded-full text-white font-bold tracking-tight shadow-lg shadow-[#6063ee]/30 hover:scale-105 active:scale-95 transition-all cursor-pointer"
              >
                Select Files
              </button>
            </>
          )}
        </div>
      </section>

      {/* Error */}
      {error && (
        <p className="text-sm text-[#ff6e84] bg-[#a70138]/10 border border-[#a70138]/30 rounded-lg px-4 py-2">
          {error}
        </p>
      )}

      {/* Parsed Content Area */}
      {resumes.length > 0 && (
        <section className="space-y-10">
          <div className="flex items-end justify-between border-b border-[#484847]/10 pb-6">
            <div className="space-y-1">
              <h2 className="text-3xl font-black tracking-tighter uppercase">Parsed Resume</h2>
              <p className="font-['Space_Grotesk'] text-xs tracking-[0.3em] text-[#53ddfc]">
                NEURAL EXTRACTION ENGINE ACTIVE
              </p>
            </div>
            <div className="text-[#adaaaa] font-['Space_Grotesk'] text-sm">
              Total Extractions: <span className="text-white font-bold">{resumes.length}</span>
            </div>
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
            {resumes.map((r) => (
              <ResumeCard
                key={r.filename}
                resume={r}
                onDelete={() => remove.mutate(r.filename)}
                deleting={remove.isPending && remove.variables === r.filename}
              />
            ))}
          </div>
        </section>
      )}
    </div>
  );
}
