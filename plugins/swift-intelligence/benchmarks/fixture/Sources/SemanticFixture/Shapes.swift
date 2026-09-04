public protocol Shape {
    func area() -> Double
}

public struct Rectangle: Shape {
    public let width: Double
    public let height: Double

    public init(width: Double, height: Double) {
        self.width = width
        self.height = height
    }

    public func area() -> Double {
        width * height
    }
}

public func totalArea(of shapes: [any Shape]) -> Double {
    shapes.reduce(0) { $0 + $1.area() }
}
