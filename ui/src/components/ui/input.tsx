import * as React from "react"
import { Input as InputPrimitive } from "@base-ui/react/input"

import { cn } from "@/lib/utils"

function Input({ className, type, style, ...props }: React.ComponentProps<"input">) {
  return (
    <InputPrimitive
      type={type}
      data-slot="input"
      className={cn(
        "h-8 w-full min-w-0 rounded-lg border px-2.5 py-1 text-sm text-white transition-colors outline-none",
        "placeholder:text-white/40",
        "focus-visible:border-white/40 focus-visible:ring-3 focus-visible:ring-white/20",
        "disabled:pointer-events-none disabled:cursor-not-allowed disabled:opacity-50",
        "file:inline-flex file:h-6 file:border-0 file:bg-transparent file:text-sm file:font-medium file:text-white",
        className
      )}
      style={{
        background: "rgba(255,255,255,0.10)",
        backdropFilter: "blur(4px)",
        WebkitBackdropFilter: "blur(4px)",
        borderColor: "rgba(255,255,255,0.20)",
        ...style,
      }}
      {...props}
    />
  )
}

export { Input }
