package org.apache.spark.sql.pipelines.conformance

import java.lang.reflect.Modifier
import java.nio.file.{Files, Paths}
import java.util.jar.JarFile
import scala.jdk.CollectionConverters._
import scala.util.Using
import scala.util.control.NonFatal
import org.json4s.DefaultFormats
import org.json4s.jackson.Serialization.{read, write}
import org.scalatest.Suite

object EnumerateSuites {
  case class Scope(className: String, sourceFiles: Vector[String], testNames: Option[Vector[String]])
  case class Entry(className: String, artifact: String, status: String,
      testNames: Vector[String], tags: Map[String, Set[String]], error: Option[String],
      positions: Map[String, String] = Map.empty, nestedSuiteIds: Vector[String] = Vector.empty,
      allTestNames: Vector[String] = Vector.empty, allTags: Map[String, Set[String]] = Map.empty,
      selection: String = "whole_suite")
  def main(args: Array[String]): Unit = {
    implicit val formats: DefaultFormats.type = DefaultFormats
    val scopes = read[Vector[Scope]](Files.readString(Paths.get(args(1)))).map(s => s.className -> s).toMap
    val loader = getClass.getClassLoader
    val rows = args.drop(2).toVector.flatMap { path =>
      Using.resource(new JarFile(path)) { jar =>
        jar.entries().asScala.map(_.getName).filter { name =>
          name.endsWith(".class") && !name.contains("$") &&
          (name.startsWith("org/apache/spark/sql/pipelines/") ||
           name.startsWith("org/apache/spark/sql/connect/pipelines/") ||
           name.startsWith("org/apache/spark/sql/hive/pipelines/") ||
           scopes.contains(name.stripSuffix(".class").replace('/', '.')))
        }.toVector.sorted.map { name =>
          val className = name.stripSuffix(".class").replace('/', '.')
          try {
            val cls = Class.forName(className, false, loader)
            if (!classOf[Suite].isAssignableFrom(cls)) {
              Entry(className, path, "not_suite", Vector.empty, Map.empty, None)
            } else if (Modifier.isAbstract(cls.getModifiers) || cls.isInterface) {
              Entry(className, path, "abstract_suite", Vector.empty, Map.empty, None)
            } else {
              val suite = cls.getConstructor().newInstance().asInstanceOf[Suite]
              val allNames = suite.testNames.toVector
              val selected = scopes.get(className).flatMap(_.testNames)
              selected.foreach { names =>
                require(names.toSet.subsetOf(allNames.toSet), "Declared SDP names missing from suite")
              }
              val names = selected.map(allowed => allNames.filter(allowed.contains)).getOrElse(allNames)
              Entry(className, path, "registered", names,
                suite.tags.filter { case (test, _) => names.contains(test) }, None,
                names.flatMap { test =>
                  suite.testDataFor(test).pos.map(pos => test -> (pos.fileName + ":" + pos.lineNumber))
                }.toMap, suite.nestedSuites.map(_.suiteId).toVector,
                allNames, suite.tags, if (selected.isDefined) "named" else "whole_suite")
            }
          } catch {
            case error if NonFatal(error) || error.isInstanceOf[LinkageError] =>
              Entry(className, path, "unresolved", Vector.empty, Map.empty,
                Some(error.toString + Option(error.getCause).map("; cause=" + _).getOrElse("")))
          }
        }
      }
    }
    require(scopes.keySet.subsetOf(rows.filter(r => r.status == "registered" && r.testNames.nonEmpty).map(_.className).toSet), "Declared SDP execution target missing, abstract, unresolved or empty")
    Files.writeString(Paths.get(args(0)), write(rows))
    println("Registered suites=" + rows.count(_.status == "registered") +
      "; scoped SDP tests=" + rows.map(_.testNames.size).sum +
      "; unresolved classes=" + rows.count(_.status == "unresolved"))
  }
}
