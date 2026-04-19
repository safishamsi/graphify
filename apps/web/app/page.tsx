import { MarketingNav } from "@/components/marketing/MarketingNav";
import { Hero } from "@/components/marketing/Hero";
import { TrustStrip } from "@/components/marketing/TrustStrip";
import { FeatureGrid } from "@/components/marketing/FeatureGrid";
import { PipelineFlow } from "@/components/marketing/PipelineFlow";
import { ConsoleMock } from "@/components/marketing/ConsoleMock";
import { BlastStory } from "@/components/marketing/BlastStory";
import { FinalCTA } from "@/components/marketing/FinalCTA";
import { MarketingFooter } from "@/components/marketing/MarketingFooter";

export default function Home() {
  return (
    <div className="marketing-surface antialiased">
      <MarketingNav />
      <main>
        <Hero />
        <TrustStrip />
        <FeatureGrid />
        <PipelineFlow />
        <ConsoleMock />
        <BlastStory />
        <FinalCTA />
      </main>
      <MarketingFooter />
    </div>
  );
}
