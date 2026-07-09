import { Badge, Button, Card, EmptyState, PageHeader, SkeletonRows } from "@/components/ui";
import { ApiError } from "@/lib/api";
import { useAcquireLicense, useMarketplaceListings, useMyLicenses } from "@/lib/hooks";
import { toastError, toastSuccess } from "@/stores/toast";
import type { MarketplaceListing } from "@/types/api";

export function MarketplacePage() {
  const { data: listings, isLoading, isError, refetch } = useMarketplaceListings();
  const { data: licenses } = useMyLicenses();
  const licensed = new Set((licenses ?? []).map((l) => l.listing_id));

  return (
    <div>
      <PageHeader
        title="Marketplace"
        description="Discover and license strategies published by the community"
      />
      {isLoading ? (
        <SkeletonRows rows={6} cols={3} />
      ) : isError ? (
        <EmptyState
          title="Marketplace could not be loaded"
          action={
            <button className="text-sm text-accent-500 hover:underline" onClick={() => refetch()}>
              Retry
            </button>
          }
        />
      ) : !listings || listings.length === 0 ? (
        <EmptyState title="No strategies are listed yet" />
      ) : (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {listings.map((listing) => (
            <ListingCard
              key={listing.id}
              listing={listing}
              owned={licensed.has(listing.id)}
            />
          ))}
        </div>
      )}
    </div>
  );
}

function ListingCard({ listing, owned }: { listing: MarketplaceListing; owned: boolean }) {
  const acquire = useAcquireLicense();
  const price =
    listing.pricing_model === "free"
      ? "Free"
      : `${listing.currency} ${Number(listing.price).toLocaleString()}`;

  const onAcquire = () =>
    acquire.mutate(listing.id, {
      onSuccess: () => toastSuccess(`Licensed “${listing.title}”`),
      onError: (error) =>
        toastError(error instanceof ApiError ? error.detail : "Could not acquire the license"),
    });

  return (
    <Card>
      <div className="flex items-start justify-between gap-2">
        <h3 className="font-semibold">{listing.title}</h3>
        <Badge color={listing.pricing_model === "free" ? "green" : "blue"}>{price}</Badge>
      </div>
      <p className="mt-1 line-clamp-3 text-sm text-slate-500">{listing.summary || "No summary."}</p>
      <div className="mt-3 flex items-center gap-3 text-xs text-slate-500">
        <span>★ {listing.average_rating.toFixed(1)} ({listing.review_count})</span>
        <span>{listing.license_count} licensed</span>
      </div>
      <div className="mt-4">
        {owned ? (
          <Badge color="green">Licensed</Badge>
        ) : (
          <Button size="sm" disabled={acquire.isPending} onClick={onAcquire}>
            {listing.pricing_model === "free" ? "Get" : "License"}
          </Button>
        )}
      </div>
    </Card>
  );
}
