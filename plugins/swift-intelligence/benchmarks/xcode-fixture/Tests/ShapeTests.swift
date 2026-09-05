import XCTest
@testable import FixtureApp

final class ShapeTests: XCTestCase {
    func testArea() {
        let rectangle = Rectangle(width: 2, height: 3)
        XCTAssertEqual(rectangle.area(), 6)
    }
}
