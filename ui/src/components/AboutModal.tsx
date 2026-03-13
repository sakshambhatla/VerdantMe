import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
} from "@/components/ui/dialog";
import { ScrollArea } from "@/components/ui/scroll-area";

interface AboutModalProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function AboutModal({ open, onOpenChange }: AboutModalProps) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl max-h-[80vh]">
        <DialogHeader>
          <DialogTitle className="text-2xl">About VerdantMe</DialogTitle>
          <DialogDescription>
            Discover companies and roles matched to your resume
          </DialogDescription>
        </DialogHeader>

        <ScrollArea className="h-[60vh] pr-4">
          <div className="space-y-6 text-sm">
            {/* Welcome */}
            <section>
              <h2 className="text-lg font-semibold mb-2">Welcome</h2>
              <p style={{ color: "rgba(255,255,255,0.80)" }}>
                <strong>VerdantMe</strong> helps you discover job opportunities by finding companies and roles
                related to your professional background. Upload your resume, and let AI-powered discovery
                help you explore career paths you might not have considered.
              </p>
              <p className="mt-2" style={{ color: "rgba(255,255,255,0.70)" }}>
                Powered by advanced language models (Claude or Gemini), VerdantMe uses semantic understanding
                to find meaningful connections between your skills and available opportunities.
              </p>
            </section>

            {/* How It Works */}
            <section>
              <h2 className="text-lg font-semibold mb-3">How It Works</h2>
              <ol className="space-y-2 list-decimal list-inside" style={{ color: "rgba(255,255,255,0.75)" }}>
                <li>
                  <strong>Upload your resume</strong> — Submit a .txt file containing your professional background,
                  skills, and experience.
                </li>
                <li>
                  <strong>Discover companies</strong> — Select or enter a company to start from, and let AI find
                  related organizations in the same industry or field.
                </li>
                <li>
                  <strong>Explore roles</strong> — Browse open positions at the discovered companies, filtered by
                  your criteria (location, title, posting date).
                </li>
                <li>
                  <strong>Analyze results</strong> — View matching roles in a searchable table, sorted by relevance.
                  Flag any problematic listings for review.
                </li>
              </ol>
            </section>

            {/* Key Features */}
            <section>
              <h2 className="text-lg font-semibold mb-3">Key Features</h2>
              <ul className="space-y-2 list-disc list-inside" style={{ color: "rgba(255,255,255,0.75)" }}>
                <li><strong>AI-powered discovery</strong> — Uses semantic analysis to find relevant companies and roles</li>
                <li><strong>Confidence filtering</strong> — Choose high, medium, or low confidence results</li>
                <li><strong>Advanced filters</strong> — Search by job title, location, and posting date</li>
                <li><strong>Sortable results</strong> — Click column headers to organize by title, location, company, etc.</li>
                <li><strong>Browser-assisted discovery</strong> — Automatically discovers deep-link job listings on company websites</li>
                <li><strong>Persistent storage</strong> — Your resume and preferences are saved locally</li>
              </ul>
            </section>

            {/* Getting Started */}
            <section>
              <h2 className="text-lg font-semibold mb-3">Getting Started</h2>
              <div className="space-y-2" style={{ color: "rgba(255,255,255,0.75)" }}>
                <p>
                  <strong>1. Configure your API</strong> — Open Preferences (⚙️) and enter your Anthropic or Gemini API key.
                  This is required for AI-powered discovery to work.
                </p>
                <p>
                  <strong>2. Upload your resume</strong> — Go to the "Upload Resume" tab and submit a .txt file.
                  Your resume is analyzed to extract skills, experience, and roles.
                </p>
                <p>
                  <strong>3. Discover companies</strong> — Switch to "Discover Companies" and search for a company you're
                  interested in or work at currently. AI will find similar companies.
                </p>
                <p>
                  <strong>4. Explore roles</strong> — Move to "Discover Roles" to see open positions at the companies found.
                  Use filters to narrow down results.
                </p>
                <p>
                  <strong>5. Apply & Connect</strong> — Review the links to job postings and apply directly through company websites.
                </p>
              </div>
            </section>

            {/* Tips */}
            <section>
              <h2 className="text-lg font-semibold mb-3">Tips & Tricks</h2>
              <ul className="space-y-2 list-disc list-inside" style={{ color: "rgba(255,255,255,0.70)" }}>
                <li>
                  <strong>Start broad, then refine:</strong> Begin with a well-known company in your field,
                  then use filters to focus on relevant roles.
                </li>
                <li>
                  <strong>Check the flagged section:</strong> Roles marked with ⚠️ may have issues with location,
                  posting date, or other inconsistencies. Review them carefully.
                </li>
                <li>
                  <strong>Adjust your career focus:</strong> In Preferences, you can add personal career goals and preferences
                  to help AI better understand what you're looking for.
                </li>
                <li>
                  <strong>Rate limiting:</strong> If you hit API rate limits, adjust the RPM (requests per minute) setting
                  in Preferences.
                </li>
                <li>
                  <strong>Use .txt resumes:</strong> Plain text resumes are parsed most accurately. Avoid PDFs or Word documents.
                </li>
              </ul>
            </section>

            {/* FAQ */}
            <section>
              <h2 className="text-lg font-semibold mb-3">FAQ</h2>
              <div className="space-y-3" style={{ color: "rgba(255,255,255,0.75)" }}>
                <div>
                  <p className="font-semibold">Is my resume stored?</p>
                  <p className="text-xs mt-1">Your resume is processed locally in your browser and stored on your device only. We don't send it to external servers.</p>
                </div>
                <div>
                  <p className="font-semibold">Do I need an API key?</p>
                  <p className="text-xs mt-1">Yes, you need either an Anthropic (Claude) or Gemini API key to use VerdantMe. You can get one free at anthropic.com or ai.google.dev.</p>
                </div>
                <div>
                  <p className="font-semibold">What format should my resume be?</p>
                  <p className="text-xs mt-1">Upload a .txt file with your resume. Plain text works best for accurate parsing.</p>
                </div>
                <div>
                  <p className="font-semibold">Can I use this on mobile?</p>
                  <p className="text-xs mt-1">VerdantMe works on mobile browsers, though the table view may require horizontal scrolling on small screens.</p>
                </div>
              </div>
            </section>
          </div>
        </ScrollArea>
      </DialogContent>
    </Dialog>
  );
}
