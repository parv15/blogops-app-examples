import Scalekit from "@scalekit-sdk/node";
import { NextRequest, NextResponse } from "next/server";

const scalekit = new Scalekit(
  process.env.SCALEKIT_ENVIRONMENT_URL!,
  process.env.SCALEKIT_CLIENT_ID!,
  process.env.SCALEKIT_CLIENT_SECRET!
);

export async function POST(req: NextRequest) {
  try {
    const { email } = await req.json();
    if (!email) {
      return NextResponse.json({ error: "Email is required." }, { status: 400 });
    }
    // Magic link URI for your app
    const magiclinkAuthUri = `${process.env.NEXT_PUBLIC_BASE_URL || "http://localhost:3000"}/api/verify-magic-link`;
    const sendResponse = await scalekit.passwordless.sendPasswordlessEmail(email, {
      expiresIn: 300,
      magiclinkAuthUri,
    });
    // Construct the magic link with both link_token and auth_request_id
    const magicLink = `${magiclinkAuthUri}?link_token=${encodeURIComponent(sendResponse.linkToken)}&auth_request_id=${encodeURIComponent(sendResponse.authRequestId)}`;
    // TODO: Send magicLink to the user's email here if not already handled by Scalekit
    return NextResponse.json({
      authRequestId: sendResponse.authRequestId,
      passwordlessType: sendResponse.passwordlessType,
      magicLink,
    });
  } catch (err: unknown) {
    const errorMessage = err instanceof Error ? err.message : "Failed to send magic link.";
    return NextResponse.json({ error: errorMessage }, { status: 500 });
  }
}
