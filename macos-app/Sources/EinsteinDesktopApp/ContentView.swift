import SwiftUI

enum WebAppLoadPhase: Equatable {
    case loading
    case ready
    case failed(String)
}

struct ContentView: View {
    @Namespace private var statusGlassNamespace
    @State private var loadPhase: WebAppLoadPhase = .loading
    @State private var reloadID = UUID()

    var body: some View {
        ZStack {
            NativeWindowBackdrop()

            NativeWebAppFrame {
                WebAppView { phase in
                    withAnimation(.easeOut(duration: 0.22)) {
                        loadPhase = phase
                    }
                }
                .id(reloadID)
            }
            .opacity(loadPhase.isBlockingFailure ? 0.34 : 1)
            .accessibilityHidden(loadPhase.isBlockingFailure)

            NativeStatusOverlay(
                phase: loadPhase,
                namespace: statusGlassNamespace,
                onRetry: {
                    withAnimation(.easeOut(duration: 0.18)) {
                        loadPhase = .loading
                        reloadID = UUID()
                    }
                }
            )
        }
        .modifier(NativeGlassWindowModifier())
    }
}

private extension WebAppLoadPhase {
    var isBlockingFailure: Bool {
        if case .failed = self {
            return true
        }
        return false
    }
}

private struct NativeWindowBackdrop: View {
    var body: some View {
        ZStack {
            Rectangle()
                .fill(.windowBackground)

            RadialGradient(
                colors: [
                    Color(red: 0.49, green: 0.89, blue: 0.77).opacity(0.16),
                    .clear
                ],
                center: .topLeading,
                startRadius: 80,
                endRadius: 720
            )

            LinearGradient(
                colors: [
                    Color.black.opacity(0.20),
                    Color.black.opacity(0.04)
                ],
                startPoint: .top,
                endPoint: .bottom
            )
        }
        .ignoresSafeArea()
    }
}

private struct NativeWebAppFrame<Content: View>: View {
    @ViewBuilder var content: () -> Content

    var body: some View {
        ZStack {
            glassFrameBackground

            content()
                .clipShape(RoundedRectangle(cornerRadius: 20, style: .continuous))
                .overlay {
                    RoundedRectangle(cornerRadius: 20, style: .continuous)
                        .strokeBorder(.white.opacity(0.10), lineWidth: 1)
                }
                .padding(8)
        }
        .padding(6)
    }

    @ViewBuilder
    private var glassFrameBackground: some View {
        // Pre-macOS-26 fallback used unconditionally. The macOS 26
        // `glassEffect` Liquid-Glass path was removed because the
        // symbols don't exist in older SDKs and the runtime
        // `if #available` guard alone doesn't help the compiler.
        // Re-introduce behind `#if compiler(>=...)` once we want to
        // ship a deliberately-gated macOS 26 polish layer.
        RoundedRectangle(cornerRadius: 28, style: .continuous)
            .fill(.regularMaterial)
            .overlay {
                RoundedRectangle(cornerRadius: 28, style: .continuous)
                    .strokeBorder(.white.opacity(0.08), lineWidth: 1)
            }
    }
}

private struct NativeStatusOverlay: View {
    let phase: WebAppLoadPhase
    let namespace: Namespace.ID
    let onRetry: () -> Void

    var body: some View {
        switch phase {
        case .loading:
            GlassEffectGroup {
                NativeStatusCard(namespace: namespace) {
                    HStack(spacing: 12) {
                        ProgressView()
                            .controlSize(.small)
                        VStack(alignment: .leading, spacing: 3) {
                            Text("Opening Carrel")
                                .font(.headline)
                            Text("Preparing the local study workspace.")
                                .font(.caption)
                                .foregroundStyle(.secondary)
                        }
                    }
                }
            }
            .transition(.opacity.combined(with: .scale(scale: 0.98)))

        case let .failed(message):
            GlassEffectGroup {
                NativeStatusCard(namespace: namespace) {
                    VStack(alignment: .leading, spacing: 14) {
                        VStack(alignment: .leading, spacing: 5) {
                            Text("Carrel could not open")
                                .font(.headline)
                            Text(message)
                                .font(.caption)
                                .foregroundStyle(.secondary)
                                .lineLimit(3)
                                .fixedSize(horizontal: false, vertical: true)
                        }

                        HStack {
                            Spacer()
                            Button {
                                onRetry()
                            } label: {
                                Label("Retry", systemImage: "arrow.clockwise")
                            }
                            .modifier(NativeGlassButtonModifier(prominent: true))
                        }
                    }
                    .frame(width: 320, alignment: .leading)
                }
            }
            .transition(.opacity.combined(with: .scale(scale: 0.98)))

        case .ready:
            EmptyView()
        }
    }
}

private struct GlassEffectGroup<Content: View>: View {
    @ViewBuilder var content: () -> Content

    var body: some View {
        // GlassEffectContainer is macOS 26+ only and not in older SDKs.
        // Pass content through unmodified on every macOS version we
        // currently target.
        content()
    }
}

private struct NativeStatusCard<Content: View>: View {
    let namespace: Namespace.ID
    @ViewBuilder var content: () -> Content

    var body: some View {
        // ultraThinMaterial fallback on every macOS version. macOS 26
        // glassEffect path removed for SDK compatibility.
        content()
            .padding(18)
            .background(.ultraThinMaterial, in: RoundedRectangle(cornerRadius: 22, style: .continuous))
            .overlay {
                RoundedRectangle(cornerRadius: 22, style: .continuous)
                    .strokeBorder(.white.opacity(0.10), lineWidth: 1)
            }
    }
}

private struct NativeGlassButtonModifier: ViewModifier {
    let prominent: Bool

    func body(content: Content) -> some View {
        // .bordered / .borderedProminent are universally available;
        // .glass / .glassProminent are macOS 26+ only and were removed
        // for SDK compatibility.
        if prominent {
            content.buttonStyle(.borderedProminent)
        } else {
            content.buttonStyle(.bordered)
        }
    }
}

private struct NativeGlassWindowModifier: ViewModifier {
    func body(content: Content) -> some View {
        // backgroundExtensionEffect + .windowBackground container are
        // macOS 26+ only and not in older SDKs. Use .windowBackground
        // material universally.
        content.background(.windowBackground)
    }
}
