import { useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { getResume, uploadResume, type ParsedResume } from "@/lib/api";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";

function ResumeCard({ resume }: { resume: ParsedResume }) {
  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="text-base">{resume.filename}</CardTitle>
        <CardDescription>
          {resume.years_of_experience != null
            ? `~${resume.years_of_experience} years experience`
            : ""}
          {" · "}Parsed {new Date(resume.parsed_at).toLocaleDateString()}
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-3">
        {resume.job_titles.length > 0 && (
          <div>
            <p className="text-xs font-medium text-white/50 mb-1">Titles</p>
            <div className="flex flex-wrap gap-1">
              {resume.job_titles.map((t) => (
                <Badge key={t} className="bg-teal-500/20 text-teal-200 border border-teal-400/30 text-xs">{t}</Badge>
              ))}
            </div>
          </div>
        )}
        {resume.skills.length > 0 && (
          <div>
            <p className="text-xs font-medium text-white/50 mb-1">Skills</p>
            <div className="flex flex-wrap gap-1">
              {resume.skills.slice(0, 20).map((s) => (
                <Badge key={s} className="bg-white/10 text-white/75 border border-white/20 text-xs">{s}</Badge>
              ))}
              {resume.skills.length > 20 && (
                <Badge className="bg-white/5 text-white/45 border border-white/15 text-xs">
                  +{resume.skills.length - 20} more
                </Badge>
              )}
            </div>
          </div>
        )}
      </CardContent>
    </Card>
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
    <div className="space-y-6">
      {/* Drop zone */}
      <div
        className={`
          relative flex flex-col items-center justify-center gap-3
          rounded-xl border-2 border-dashed p-12 text-center cursor-pointer
          transition-colors
          ${dragging
            ? "border-white/60 bg-white/15"
            : "border-white/25 hover:border-white/45 hover:bg-white/10"
          }
          ${upload.isPending ? "pointer-events-none opacity-60" : ""}
        `}
        style={{ backdropFilter: "blur(8px)", WebkitBackdropFilter: "blur(8px)" }}
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
            <div className="h-8 w-8 animate-spin rounded-full border-4 border-white/60 border-t-transparent" />
            <p className="text-sm text-white/60">Parsing resume…</p>
          </>
        ) : (
          <>
            <div className="text-4xl">📄</div>
            <div>
              <p className="font-medium text-white">Drop your resume here</p>
              <p className="text-sm text-white/55">or click to browse — .txt files only</p>
              <p className="text-xs text-white/40 mt-1">
                Uploading replaces any existing resume
              </p>
            </div>
          </>
        )}
      </div>

      {error && (
        <p className="text-sm text-red-300 bg-red-500/15 border border-red-400/25 rounded-lg px-4 py-2">{error}</p>
      )}

      {resumes.length > 0 && (
        <div className="space-y-3">
          <h3 className="font-semibold text-sm text-white/50 uppercase tracking-wide">
            Parsed Resume
          </h3>
          {resumes.map((r) => <ResumeCard key={r.filename} resume={r} />)}
        </div>
      )}
    </div>
  );
}
