// Render each page of a PDF to PNG and print the page count + extracted text (what an ATS reads).
// Usage: osascript -l JavaScript pdf_pages.js <pdf> <outdir>
ObjC.import('PDFKit'); ObjC.import('AppKit');
function run(argv) {
  var doc = $.PDFDocument.alloc.initWithURL($.NSURL.fileURLWithPath(argv[0]));
  var n = doc.pageCount;
  for (var i = 0; i < n; i++) {
    var page = doc.pageAtIndex(i);
    var img = page.thumbnailOfSizeForBox($.NSMakeSize(1100, 1424), $.kPDFDisplayBoxMediaBox);
    var rep = $.NSBitmapImageRep.imageRepWithData(img.TIFFRepresentation);
    var png = rep.representationUsingTypeProperties($.NSBitmapImageFileTypePNG, $({}));
    png.writeToFileAtomically(argv[1] + '/page' + (i + 1) + '.png', true);
  }
  return 'PAGES ' + n + '\n' + doc.string.js;
}
